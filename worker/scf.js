function bytesToBase64(bytes) {
  return Buffer.from(bytes).toString("base64");
}

function parseBody(event) {
  if (!event) {
    return {};
  }
  if (typeof event === "string") {
    return JSON.parse(event);
  }
  if (event.body !== undefined) {
    const raw = event.isBase64Encoded
      ? Buffer.from(event.body, "base64").toString("utf8")
      : event.body;
    if (typeof raw === "string" && raw) {
      return JSON.parse(raw);
    }
    if (raw && typeof raw === "object") {
      return raw;
    }
  }
  if (event.type || event.header || event.challenge) {
    return event;
  }
  return {};
}

function json(status, payload) {
  return {
    isBase64Encoded: false,
    statusCode: status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: typeof payload === "string" ? payload : JSON.stringify(payload),
  };
}

export const main_handler = async (event) => {
  let body;
  try {
    body = parseBody(event);
  } catch {
    return json(400, { error: "bad json" });
  }

  const got = (body.header && body.header.token) || body.token || "";
  const expected = process.env.FEISHU_VERIFICATION_TOKEN || "";
  if (!expected || got !== expected) {
    return json(401, { error: "forbidden" });
  }

  if (body.type === "url_verification" && body.challenge) {
    return json(200, { challenge: body.challenge });
  }

  const repo = process.env.GITHUB_REPO || "";
  const githubToken = process.env.GITHUB_TOKEN || "";
  if (!repo || !githubToken) {
    return json(500, { error: "missing github config" });
  }

  const eventType = (body.header && body.header.event_type) || body.type || "unknown";
  const encoded = bytesToBase64(Buffer.from(JSON.stringify(body)));
  let response;
  let text = "";
  try {
    response = await fetch(
      `https://api.github.com/repos/${repo}/actions/workflows/message.yml/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${githubToken}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          "User-Agent": "legal-daily",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({
          ref: "main",
          inputs: { event_b64: encoded },
        }),
      }
    );
    text = await response.text();
  } catch (error) {
    return json(502, { error: "github unreachable", detail: String(error).slice(0, 180) });
  }

  if (response.status !== 204) {
    return json(502, {
      error: "dispatch failed",
      status: response.status,
      eventType,
      detail: text.slice(0, 180),
    });
  }
  return json(200, { ok: true, eventType });
};
