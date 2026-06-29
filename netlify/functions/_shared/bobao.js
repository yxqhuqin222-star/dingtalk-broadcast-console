const crypto = require("crypto");

const DEFAULT_KEYWORD = "成单";
const DEFAULT_TEMPLATE = "{keyword} 小学1元-纷格进量：{count}";

function json(statusCode, payload) {
  return {
    statusCode,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
    body: JSON.stringify(payload),
  };
}

function parseMultipart(event) {
  const contentType = event.headers["content-type"] || event.headers["Content-Type"] || "";
  const boundaryMatch = contentType.match(/boundary=(?:"([^"]+)"|([^;]+))/i);
  if (!boundaryMatch) throw new Error("缺少 multipart boundary。");

  const boundary = Buffer.from(`--${boundaryMatch[1] || boundaryMatch[2]}`);
  const body = event.isBase64Encoded
    ? Buffer.from(event.body || "", "base64")
    : Buffer.from(event.body || "", "utf8");
  const fields = {};
  const files = {};
  let offset = 0;

  while (offset < body.length) {
    const start = body.indexOf(boundary, offset);
    if (start === -1) break;
    let partStart = start + boundary.length;
    if (body.slice(partStart, partStart + 2).toString() === "--") break;
    if (body.slice(partStart, partStart + 2).toString() === "\r\n") partStart += 2;

    const next = body.indexOf(boundary, partStart);
    if (next === -1) break;
    let part = body.slice(partStart, next);
    if (part.slice(-2).toString() === "\r\n") part = part.slice(0, -2);

    const headerEnd = part.indexOf(Buffer.from("\r\n\r\n"));
    if (headerEnd !== -1) {
      const headerText = part.slice(0, headerEnd).toString("utf8");
      const payload = part.slice(headerEnd + 4);
      const disposition = headerText.match(/content-disposition:[^\r\n]+/i)?.[0] || "";
      const name = disposition.match(/name="([^"]+)"/)?.[1];
      const filename = disposition.match(/filename="([^"]*)"/)?.[1];
      if (name && filename) files[name] = payload;
      if (name && !filename) fields[name] = payload.toString("utf8");
    }
    offset = next;
  }

  return { fields, files };
}

function decodeCsv(data) {
  let lastError = null;
  for (const encoding of ["utf-8", "gb18030", "gbk"]) {
    try {
      return new TextDecoder(encoding, { fatal: true }).decode(data).replace(/^\uFEFF/, "");
    } catch (error) {
      lastError = error;
    }
  }
  throw new Error(`无法识别 CSV 编码：${lastError?.message || "unknown error"}`);
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (quoted) {
      if (char === '"' && next === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }

  if (field || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }

  const headers = rows.shift() || [];
  return rows
    .filter((item) => item.some((value) => value !== ""))
    .map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] || ""])));
}

function parseValues(column, rawValue) {
  const value = String(rawValue || "").trim();
  if (value.includes(",") || value.includes("，")) {
    return new Set(value.replace(/，/g, ",").split(",").map((item) => item.trim()).filter(Boolean));
  }
  if (column === "课程年级") {
    return new Set(value.replace(/年级/g, "").split("").filter((item) => item.trim()).map((item) => `${item}年级`));
  }
  if (value.includes("|")) {
    return new Set(value.split("|").map((item) => item.trim()).filter(Boolean));
  }
  return new Set([value]);
}

function buildFilters(fields) {
  const filters = [];
  for (const index of [1, 2]) {
    const column = String(fields[`filterColumn${index}`] || "").trim();
    const value = String(fields[`filterValue${index}`] || "").trim();
    if (column && value) filters.push([column, parseValues(column, value)]);
  }
  return filters;
}

function countRowsByFilters(rows, filters, amountColumn, amountValue) {
  const targetAmount = Number(amountValue);
  let count = 0;
  for (const row of rows) {
    const matched = filters.every(([column, allowedValues]) => allowedValues.has(row[column]));
    if (matched && Number(row[amountColumn]) === targetAmount) count += 1;
  }
  return count;
}

function buildMessagePayload(rows, fields) {
  const filters = buildFilters(fields);
  const amountColumn = String(fields.amountColumn || "订单实付金额").trim();
  const amountValue = String(fields.amountValue || "1").trim();
  const keyword = String(fields.keyword || DEFAULT_KEYWORD).trim();
  const template = String(fields.template || DEFAULT_TEMPLATE).trim();
  const count = countRowsByFilters(rows, filters, amountColumn, amountValue);
  const message = template.replaceAll("{keyword}", keyword).replaceAll("{count}", String(count));
  return { message, count };
}

function parseCsvValues(value) {
  if (!value) return [];
  return String(value).replace(/，/g, ",").split(",").map((item) => item.trim()).filter(Boolean);
}

function addAtText(message, atMobiles = [], atUserIds = [], isAtAll = false) {
  if (isAtAll) return message.includes("@所有人") ? message : `${message} @所有人`;
  const atParts = [...atMobiles, ...atUserIds].map((item) => `@${item}`);
  const missingParts = atParts.filter((part) => !message.includes(part));
  return missingParts.length ? `${message} ${missingParts.join(" ")}` : message;
}

function signedWebhook(webhook, secret) {
  if (!secret) return webhook;
  const timestamp = String(Date.now());
  const digest = crypto.createHmac("sha256", secret).update(`${timestamp}\n${secret}`).digest("base64");
  const separator = webhook.includes("?") ? "&" : "?";
  return `${webhook}${separator}timestamp=${timestamp}&sign=${encodeURIComponent(digest)}`;
}

async function sendDingtalkMessage(message, fields) {
  const webhook = process.env.DINGTALK_WEBHOOK;
  if (!webhook) throw new Error("Missing DINGTALK_WEBHOOK environment variable.");

  const atMobiles = parseCsvValues(fields.atMobiles || "");
  const atUserIds = parseCsvValues(fields.atUserIds || "");
  const isAtAll = ["1", "true", "on", "yes"].includes(String(fields.isAtAll || "").toLowerCase());
  const finalMessage = addAtText(message, atMobiles, atUserIds, isAtAll);
  const response = await fetch(signedWebhook(webhook, process.env.DINGTALK_SECRET), {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify({
      msgtype: "text",
      text: { content: finalMessage },
      at: { atMobiles, atUserIds, isAtAll },
    }),
  });
  const result = await response.json();
  return { finalMessage, result };
}

function payloadFromEvent(event) {
  const { fields, files } = parseMultipart(event);
  const fileData = files.file;
  if (!fileData) throw new Error("请先上传 CSV 文件");
  const rows = parseCsv(decodeCsv(fileData));
  const { message, count } = buildMessagePayload(rows, fields);
  return { fields, rows, message, count };
}

module.exports = {
  json,
  payloadFromEvent,
  sendDingtalkMessage,
};
