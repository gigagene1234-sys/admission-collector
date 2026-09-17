const WORKERS_AI_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";
const WORKERS_AI_FALLBACK_MODEL = "@cf/openai/gpt-oss-120b";

const ALLOWED_ORIGINS = new Set([
  "https://wsu-rail-interview-33.vercel.app",
  "https://wsu-rail-interview-33-suneung.vercel.app",
]);

const MAX_BODY_BYTES = 450_000;
const MAX_RECORDS = 8;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return handleOptions(request);
    }

    if (url.pathname === "/health" && request.method === "GET") {
      return json(
        {
          ok: true,
          service: "wsu-interview-ai",
          version: "1.2.0",
          providers: {
            workersAI: Boolean(env.AI),
          },
          models: {
            primary: WORKERS_AI_MODEL,
            fallback: WORKERS_AI_FALLBACK_MODEL,
          },
        },
        200,
        request
      );
    }

    if (url.pathname !== "/api/rewrite") {
      return json({ error: "Not found" }, 404, request);
    }

    if (request.method !== "POST") {
      return json({ error: "POST만 지원합니다." }, 405, request);
    }

    const origin = request.headers.get("Origin");
    if (origin && !ALLOWED_ORIGINS.has(origin)) {
      return json({ error: "허용되지 않은 Origin입니다." }, 403, request);
    }

    const declaredLength = Number(request.headers.get("Content-Length") || 0);
    if (declaredLength > MAX_BODY_BYTES) {
      return json({ error: "요청 본문이 너무 큽니다." }, 413, request);
    }

    let payload;
    try {
      payload = await request.json();
    } catch {
      return json({ error: "잘못된 JSON입니다." }, 400, request);
    }

    let input;
    try {
      input = normalizeRequest(payload);
    } catch (error) {
      return json({ error: String(error?.message || error) }, 400, request);
    }

    const prompt = buildPrompt(input);

    if (!env.AI) {
      return json({ error: "Cloudflare Workers AI binding이 설정되지 않았습니다." }, 503, request);
    }

    try {
      const { model, result } = await callWorkersAI(prompt, env.AI);
      return json(
        {
          source: "cloudflare-workers-ai",
          model,
          ...result,
        },
        200,
        request
      );
    } catch (error) {
      console.error("Cloudflare Workers AI failed", error);
      return json(
        {
          error: "AI 수정안 생성에 실패했습니다.",
          diagnostics: [compact(error?.message || error)],
        },
        502,
        request
      );
    }
  },
};

function normalizeRequest(payload) {
  const question = payload?.question || {};
  const id = Number(question.id || payload?.questionId || 0);
  const text = safeText(question.text || payload?.question, 2000);
  if (!text) throw new Error("질문이 비어 있습니다.");

  const recordsRaw = Array.isArray(payload?.records)
    ? payload.records
    : Array.isArray(payload?.selectedActivities)
      ? payload.selectedActivities
      : [];

  const records = recordsRaw.slice(0, MAX_RECORDS).map((record, index) => ({
    id: safeText(record?.id || `record-${index + 1}`, 200),
    subject: safeText(record?.subject, 300),
    title: safeText(record?.title, 500),
    sourceKind: safeText(record?.sourceKind || record?.sourceStatus, 100),
    sourceLabel: safeText(record?.sourceLabel, 300),
    summary: safeText(record?.summary, 5000),
    fullText: safeText(record?.fullText, 12000),
    limits: safeText(record?.limits || record?.limit, 4000),
  }));

  return {
    question: {
      id,
      text,
      target: safeText(question.target || payload?.target, 4000),
      method: safeText(question.method || payload?.method, 4000),
      risk: safeText(question.risk || payload?.risk, 4000),
    },
    currentAnswer: safeText(payload?.currentAnswer, 12000),
    userInstruction: safeText(payload?.userInstruction || payload?.userOpinion, 6000),
    records,
  };
}

function safeText(value, maxLength) {
  if (value == null) return "";
  return String(value).trim().slice(0, maxLength);
}

function buildPrompt(input) {
  const recordsText = input.records.length
    ? input.records
        .map((record, index) => {
          const source = record.sourceLabel || record.sourceKind || "출처 미표기";
          return [
            `### 근거 ${index + 1}`,
            `- 과목/영역: ${record.subject || "미표기"}`,
            `- 활동명: ${record.title || "미표기"}`,
            `- 출처 상태: ${source}`,
            `- 요약: ${record.summary || "없음"}`,
            `- 원문: ${record.fullText || "원문 미제공"}`,
            `- 과장 방지선: ${record.limits || "제공된 기록 밖의 성과·수치·완료 여부를 추가하지 않음"}`,
          ].join("\n");
        })
        .join("\n\n")
    : "선택된 생기부 근거 없음";

  return `당신은 2027학년도 우송대학교 철도차량시스템학과 교과면접 답안 전용 첨삭자입니다.

[절대 규칙]
1. 제공된 현재 답안, 질문 정보, 선택 근거에 없는 사실·수치·성과·실험 완료 여부를 새로 만들지 마세요.
2. sourceKind/sourceLabel이 official이면 공식 발급본 근거, draft이면 별도 작성본으로 취급하고 최종 공식 기록과 동일하다고 말하지 마세요. unlinked 또는 원문 미연결 자료는 공식 학생부 문구처럼 표현하지 마세요.
3. '계획했다/구상했다/설계했다'와 '제작했다/실행했다/검증했다'를 엄격히 구분하세요.
4. 기관사를 정비사·시설관리자처럼 묘사하지 마세요. 기관사의 역할은 운전, 운행 중 상태 확인, 절차 준수, 이상 징후 확인·보고 등 실제 역할 범위에서 표현하세요.
5. 모든 답을 억지로 철도나 개인 활동과 연결하지 마세요. 지식·판단형 질문은 질문 자체에 먼저 답하고, 활동은 자연스러울 때만 보조 근거로 사용하세요.
6. 사용자의 수정 의견을 무조건 따르지 마세요. 질문 적합성, 사실성, 면접 전달력에 맞지 않으면 assessment에서 이유를 설명하고 더 나은 방향으로 수정하세요.
7. 기존 답안의 좋은 부분은 유지하고, 사용자가 요청한 변화와 선택 근거 때문에 필요한 부분만 수정하세요.
8. 활동 나열보다 '무엇을 인식했고 → 어떻게 판단/행동했고 → 무엇을 배웠는가'가 드러나게 하세요.
9. 학생이 실제 면접에서 말할 수 있는 자연스러운 한국어 구어체로 작성하세요. 지나치게 논문식이거나 과장된 표현은 피하세요.
10. 선택되지 않은 다른 생기부 활동을 새로 끌어오지 마세요.

[질문]
Q${input.question.id || "?"}. ${input.question.text}

[질문이 원하는 답]
${input.question.target || "별도 지침 없음"}

[기존 작성 방식]
${input.question.method || "별도 지침 없음"}

[주의/위험요소]
${input.question.risk || "별도 지침 없음"}

[현재 답안]
${input.currentAnswer || "현재 답안 없음"}

[사용자 수정 의견]
${input.userInstruction || "별도 의견 없음"}

[사용자가 직접 선택한 근거]
${recordsText}

[출력 규칙]
반드시 아래 세 필드만 포함하는 JSON 객체로 응답하세요.
{
  "assessment": "사용자 의견 및 근거 선택이 질문에 적합한지 비판적으로 검토한 결과. 2~5문장.",
  "caution": "출처·역할·과장·미확인 사실과 관련해 실제 주의할 점. 없으면 빈 문자열.",
  "revisedAnswer": "수정된 전체 면접 답안"
}`;
}

async function callWorkersAI(prompt, ai) {
  const messages = [
    {
      role: "system",
      content: "입시 면접 답안을 근거 기반으로 첨삭합니다. 반드시 순수 JSON 객체만 반환하세요.",
    },
    { role: "user", content: prompt },
  ];

  const models = [WORKERS_AI_MODEL, WORKERS_AI_FALLBACK_MODEL];
  let lastError;

  for (const model of models) {
    try {
      const options = {
        messages,
        max_tokens: 1800,
        temperature: 0.2,
      };

      if (model === WORKERS_AI_MODEL) {
        options.response_format = {
          type: "json_schema",
          json_schema: {
            type: "object",
            properties: {
              assessment: { type: "string" },
              caution: { type: "string" },
              revisedAnswer: { type: "string" },
            },
            required: ["assessment", "caution", "revisedAnswer"],
          },
        };
      }

      const data = await ai.run(model, options);
      const response = data?.response ?? data;

      if (response && typeof response === "object" && !Array.isArray(response)) {
        return {
          model,
          result: normalizeModelResult(response),
        };
      }

      const text = typeof response === "string" ? response : "";
      if (!text) {
        throw new Error(`${model} 응답 내용 없음`);
      }

      return {
        model,
        result: normalizeModelResult(parseJsonObject(text)),
      };
    } catch (error) {
      lastError = error;
      console.error(`Workers AI model failed: ${model}`, error);
    }
  }

  throw lastError || new Error("Workers AI 모델 호출 실패");
}

function parseJsonObject(text) {
  const trimmed = String(text || "").trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    const start = trimmed.indexOf("{");
    const end = trimmed.lastIndexOf("}");
    if (start >= 0 && end > start) {
      return JSON.parse(trimmed.slice(start, end + 1));
    }
    throw new Error("모델 응답이 JSON 객체가 아닙니다.");
  }
}

function normalizeModelResult(value) {
  const assessment = safeText(value?.assessment || value?.opinionReview, 5000);
  const caution = safeText(value?.caution || value?.cautions, 5000);
  const revisedAnswer = safeText(value?.revisedAnswer || value?.newAnswer, 16000);
  if (!revisedAnswer) throw new Error("모델이 revisedAnswer를 반환하지 않았습니다.");
  return { assessment, caution, revisedAnswer };
}

function compact(value) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, 500);
}

function handleOptions(request) {
  const origin = request.headers.get("Origin");
  if (origin && !ALLOWED_ORIGINS.has(origin)) {
    return new Response(null, { status: 403 });
  }
  return new Response(null, {
    status: 204,
    headers: corsHeaders(origin),
  });
}

function corsHeaders(origin) {
  const allowedOrigin = origin && ALLOWED_ORIGINS.has(origin) ? origin : "https://wsu-rail-interview-33.vercel.app";
  return {
    "Access-Control-Allow-Origin": allowedOrigin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function json(value, status, request) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store, max-age=0",
      "X-Content-Type-Options": "nosniff",
      ...corsHeaders(request.headers.get("Origin")),
    },
  });
}
