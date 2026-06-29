const { json, payloadFromEvent, sendDingtalkMessage } = require("./_shared/bobao");

exports.handler = async (event) => {
  if (event.httpMethod === "OPTIONS") return json(204, {});
  if (event.httpMethod !== "POST") return json(405, { ok: false, error: "Method not allowed" });

  try {
    const { fields, rows, message, count } = payloadFromEvent(event);
    const { finalMessage, result } = await sendDingtalkMessage(message, fields);
    return json(200, {
      ok: result.errcode === 0,
      message: finalMessage,
      count,
      dingtalk: result,
      rows: rows.length,
    });
  } catch (error) {
    return json(500, { ok: false, error: error.message });
  }
};
