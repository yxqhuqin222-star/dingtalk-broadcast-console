const { json, payloadFromEvent } = require("./_shared/bobao");

exports.handler = async (event) => {
  if (event.httpMethod === "OPTIONS") return json(204, {});
  if (event.httpMethod !== "POST") return json(405, { ok: false, error: "Method not allowed" });

  try {
    const { rows, message, count } = payloadFromEvent(event);
    return json(200, { ok: true, message, count, rows: rows.length });
  } catch (error) {
    return json(500, { ok: false, error: error.message });
  }
};
