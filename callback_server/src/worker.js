// Jovinna POS — M-Pesa callback server (Cloudflare Worker + D1).
//
// Safaricom posts each STK Push result to:   POST /mpesa/callback/<CALLBACK_PATH>
// The POS app reads one payment's result:   GET  /mpesa/result/<CheckoutRequestID>
//                                            with header  Authorization: Bearer <APP_KEY>
//
// APP_KEY is a secret set with `wrangler secret put APP_KEY`. CALLBACK_PATH is derived from it
// (first 24 hex characters of SHA-256 of the key), so the callback address can't be guessed and only
// one secret has to be managed. Payment details are only ever given to callers holding APP_KEY.

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });

async function callbackPath(key) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(key));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 24);
}

// Constant-time comparison, so the key can't be worked out from response timings
function sameSecret(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function metadata(items) {
  const out = {};
  for (const item of items || []) out[item.Name] = item.Value;
  return out;
}

export default {
  async fetch(request, env) {
    if (!env.APP_KEY) return json({ error: "Server not set up: APP_KEY secret missing" }, 500);
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);

    // ---- Safaricom → us ----
    if (request.method === "POST" && parts[0] === "mpesa" && parts[1] === "callback") {
      if (parts[2] !== (await callbackPath(env.APP_KEY))) return json({ error: "Not found" }, 404);
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ ResultCode: 1, ResultDesc: "Invalid JSON" }, 400);
      }
      const cb = body?.Body?.stkCallback;
      if (!cb?.CheckoutRequestID) return json({ ResultCode: 1, ResultDesc: "Not an STK callback" }, 400);
      const meta = metadata(cb.CallbackMetadata?.Item);
      await env.DB.prepare(
        `INSERT INTO payments (checkout_id, result_code, result_desc, receipt, amount, phone, paid_at, received_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
         ON CONFLICT(checkout_id) DO UPDATE SET result_code = excluded.result_code,
           result_desc = excluded.result_desc, receipt = excluded.receipt, amount = excluded.amount,
           phone = excluded.phone, paid_at = excluded.paid_at, received_at = excluded.received_at`
      ).bind(
        cb.CheckoutRequestID, Number(cb.ResultCode), cb.ResultDesc ?? "",
        meta.MpesaReceiptNumber ?? null, meta.Amount ?? null,
        meta.PhoneNumber != null ? String(meta.PhoneNumber) : null,
        meta.TransactionDate != null ? String(meta.TransactionDate) : null
      ).run();
      // Safaricom expects this acknowledgement
      return json({ ResultCode: 0, ResultDesc: "Accepted" });
    }

    // ---- POS app → us ----
    if (request.method === "GET" && parts[0] === "mpesa" && parts[1] === "result" && parts[2]) {
      const auth = request.headers.get("authorization") || "";
      if (!sameSecret(auth.replace(/^Bearer\s+/i, ""), env.APP_KEY)) return json({ error: "Unauthorized" }, 401);
      const row = await env.DB.prepare(
        "SELECT checkout_id, result_code, result_desc, receipt, amount, phone, paid_at FROM payments WHERE checkout_id = ?"
      ).bind(parts[2]).first();
      return row ? json(row) : json({ status: "waiting" }, 404);
    }

    // Health check for the app's "Test connection" button
    if (request.method === "GET" && url.pathname === "/health") {
      const auth = request.headers.get("authorization") || "";
      if (!sameSecret(auth.replace(/^Bearer\s+/i, ""), env.APP_KEY)) return json({ error: "Unauthorized" }, 401);
      return json({ ok: true, callback_path: `/mpesa/callback/${await callbackPath(env.APP_KEY)}` });
    }

    return json({ error: "Not found" }, 404);
  },

  // Daily clean-up: payment records are only needed until the sale is saved in the POS
  async scheduled(event, env) {
    await env.DB.prepare("DELETE FROM payments WHERE received_at < datetime('now', '-90 days')").run();
  },
};
