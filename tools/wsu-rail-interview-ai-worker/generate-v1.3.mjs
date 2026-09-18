import fs from "node:fs";
import zlib from "node:zlib";
import crypto from "node:crypto";

const payload = "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";
const rawSource = zlib.gunzipSync(Buffer.from(payload, "base64"));
const rawHash = crypto.createHash("sha256").update(rawSource).digest("hex");
const expected = "b2acf745d6a381ee533f23084a6cfc8df70ffa6aaf6c0c9488ecab0d2a646432";
if (rawHash !== expected) throw new Error(`Generated Worker source hash mismatch: ${rawHash}`);

let sourceText = rawSource.toString("utf8");

const glmPromptMarker = '{ role: "user", content: buildGLMPrompt(input) },';
if (!sourceText.includes(glmPromptMarker)) throw new Error("GLM prompt patch target not found");
sourceText = sourceText.replace(
  glmPromptMarker,
  '{ role: "user", content: buildGLMTextPrompt(input) },'
);

const glmTextBlock = `      const revisedAnswer = extractModelText(data);
      if (!revisedAnswer) throw new Error("GLM이 수정 답안 본문을 반환하지 않았습니다.");

      return {
        assessment: "요청의 핵심과 기존 답안을 바탕으로 기본 첨삭을 수행했습니다.",
        caution: "",
        revisedAnswer,
        riskFlags: []
      };`;
const callGlmStart = sourceText.indexOf("async function callGLM");
const callGlmEnd = sourceText.indexOf("function buildLlamaVerifierPrompt", callGlmStart);
if (callGlmStart < 0 || callGlmEnd < 0) throw new Error("callGLM boundaries not found");
let callGlmSource = sourceText.slice(callGlmStart, callGlmEnd);
const glmParsePattern = /const parsed = parseModelPayload\(data\);[\s\S]*?return normalized;/;
if (!glmParsePattern.test(callGlmSource)) throw new Error("GLM parse block target not found");
callGlmSource = callGlmSource.replace(glmParsePattern, glmTextBlock.trim());
sourceText = sourceText.slice(0, callGlmStart) + callGlmSource + sourceText.slice(callGlmEnd);
sourceText = sourceText.replaceAll("1.3.1", "1.3.6");

sourceText += `

function buildGLMTextPrompt(input) {
  return baseRules() + "\\n\\n" +
    commonInputText(input) + "\\n\\n" +
    "[작업] 사용자의 수정 요구가 질문 의도와 근거에 맞는 범위에서 기존 답안의 좋은 부분을 최대한 유지하여 전체 답안을 다듬으세요. " +
    "기록에 없는 사실·수치·성과를 추가하지 마세요. " +
    "출력에는 수정된 전체 답안 본문만 적고, 설명·평가·주의사항·JSON·마크다운·머리말은 넣지 마세요.";
}

function extractModelText(value) {
  if (typeof value === "string") return value.trim();
  if (typeof value?.response === "string") return value.response.trim();
  if (typeof value?.response?.response === "string") return value.response.response.trim();
  const content = value?.choices?.[0]?.message?.content;
  if (typeof content === "string") return content.trim();
  if (Array.isArray(content)) {
    return content.map((part) => typeof part === "string" ? part : (part?.text || "")).join("").trim();
  }
  return "";
}
`;


// v1.4.0: remove the external critic stage and keep a two-model pipeline only.
const twoModelFetch = [
  "export default {",
  "  async fetch(request, env) {",
  "    const url = new URL(request.url);",
  "    if (request.method === \"OPTIONS\") return handleOptions(request);",
  "    if (url.pathname === \"/health\" && request.method === \"GET\") {",
  "      return json({",
  "        ok: true,",
  "        service: \"wsu-interview-ai\",",
  "        version: \"1.4.0\",",
  "        providers: { workersAI: Boolean(env.AI) },",
  "        routing: { default: \"glm\", verification: \"risk-based-llama\" },",
  "        models: { generation: GLM_MODEL, verifier: LLAMA_MODEL },",
  "      }, 200, request);",
  "    }",
  "    if (request.method === \"GET\" && url.pathname === \"/\") return serveInterviewApp(request);",
  "    if (request.method === \"GET\" && url.pathname === \"/ai-ui.js\") return new Response(AI_UI_JS, { status: 200, headers: { \"Content-Type\": \"application/javascript; charset=utf-8\", \"Cache-Control\": \"no-store, max-age=0\" } });",
  "    if (url.pathname !== \"/api/rewrite\") return json({ error: \"Not found\" }, 404, request);",
  "    if (request.method !== \"POST\") return json({ error: \"POST만 지원합니다.\" }, 405, request);",
  "    const origin = request.headers.get(\"Origin\");",
  "    if (origin && !ALLOWED_ORIGINS.has(origin)) return json({ error: \"허용되지 않은 Origin입니다.\" }, 403, request);",
  "    const declaredLength = Number(request.headers.get(\"Content-Length\") || 0);",
  "    if (declaredLength > MAX_BODY_BYTES) return json({ error: \"요청 본문이 너무 큽니다.\" }, 413, request);",
  "    let payload;",
  "    try { payload = await request.json(); } catch { return json({ error: \"잘못된 JSON입니다.\" }, 400, request); }",
  "    let input;",
  "    try { input = normalizeRequest(payload); } catch (error) { return json({ error: String(error?.message || error) }, 400, request); }",
  "    if (!env.AI) return json({ error: \"Cloudflare Workers AI binding이 설정되지 않았습니다.\" }, 503, request);",
  "    const preRisk = assessRisk(input, \"\");",
  "    let draft;",
  "    try {",
  "      draft = await callGLM(input, env.AI, preRisk.level);",
  "    } catch (error) {",
  "      console.error(\"GLM generation failed\", compact(error?.message || error));",
  "      const risk = mergeRisk(preRisk, { score: 3, reasons: [\"GLM 호출 실패\"] });",
  "      try {",
  "        const result = await callLlamaDirect(input, env.AI, [\"GLM 호출 실패로 Llama가 직접 작성\"]);",
  "        return json({ source: \"cloudflare-workers-ai\", model: LLAMA_MODEL, reviewPath: [\"llama-direct-fallback\"], risk, ...result }, 200, request);",
  "      } catch (fallbackError) {",
  "        return json({ error: \"AI 수정안 생성에 실패했습니다.\", diagnostics: [compact(fallbackError?.message || fallbackError)] }, 502, request);",
  "      }",
  "    }",
  "    const postRisk = assessRisk(input, draft.revisedAnswer);",
  "    const risk = mergeRisk(preRisk, postRisk);",
  "    const needsVerification = risk.level !== \"low\" || !looksComplete(draft.revisedAnswer);",
  "    if (!needsVerification) {",
  "      return json({ source: \"cloudflare-workers-ai\", model: GLM_MODEL, reviewPath: [\"glm\"], risk, assessment: draft.assessment, caution: draft.caution, revisedAnswer: draft.revisedAnswer }, 200, request);",
  "    }",
  "    try {",
  "      const verified = await callLlamaVerifier(input, draft, risk, env.AI);",
  "      return json({ source: \"multi-model\", model: LLAMA_MODEL, models: { generation: GLM_MODEL, verifier: LLAMA_MODEL }, reviewPath: [\"glm\", \"llama-verifier\"], risk, ...verified }, 200, request);",
  "    } catch (error) {",
  "      console.error(\"Llama verification failed\", compact(error?.message || error));",
  "      return json({ error: \"AI 수정안 검증에 실패했습니다.\", diagnostics: [compact(error?.message || error)] }, 502, request);",
  "    }",
  "  },",
  "};",
].join("\n");

const fetchStart = sourceText.indexOf("export default {");
const normalizeStart = sourceText.indexOf("function normalizeRequest", fetchStart);
if (fetchStart < 0 || normalizeStart < 0) throw new Error("fetch router boundaries not found");
sourceText = sourceText.slice(0, fetchStart) + twoModelFetch + "\n\n" + sourceText.slice(normalizeStart);

const verifierStart = sourceText.indexOf("function buildLlamaVerifierPrompt");
const directStart = sourceText.indexOf("async function callLlamaDirect", verifierStart);
if (verifierStart < 0 || directStart < 0) throw new Error("verifier boundaries not found");
const twoModelVerifier = [
  "function buildLlamaVerifierPrompt(input, draft, risk) {",
  "  return baseRules() + \"\\n\\n\" +",
  "    \"[검증자 역할]\\n\" +",
  "    \"아래 GLM 초안은 제안일 뿐 사실 근거가 아닙니다. 사실 여부는 반드시 원래 질문·현재 답안·사용자가 선택한 근거에서만 확인하세요. \" +",
  "    \"각 근거의 limits는 절대 금지선입니다. limits와 충돌하는 표현은 반드시 삭제하거나 근거 수준으로 낮추세요. \" +",
  "    \"근거 없는 사실·수치·완료 표현과 기관사 역할을 벗어난 표현도 제거하세요.\\n\\n\" +",
  "    commonInputText(input) + \"\\n\\n\" +",
  "    \"[자동 위험도]\\n\" + JSON.stringify(risk) + \"\\n\\n\" +",
  "    \"[GLM 초안]\\n\" + JSON.stringify(draft) + \"\\n\\n\" +",
  "    \"[최종 출력]\\nassessment, caution, revisedAnswer 세 필드만 반환하세요.\";",
  "}",
  "",
  "async function callLlamaVerifier(input, draft, risk, ai) {",
  "  return callLlamaStructured(buildLlamaVerifierPrompt(input, draft, risk), ai);",
  "}",
  "",
].join("\n");
sourceText = sourceText.slice(0, verifierStart) + twoModelVerifier + sourceText.slice(directStart);

const externalCriticStart = sourceText.indexOf("async function callGeminiCritic");
const parserStart = sourceText.indexOf("function parseModelPayload", externalCriticStart);
if (externalCriticStart >= 0) {
  if (parserStart < 0) throw new Error("external critic removal boundary not found");
  sourceText = sourceText.slice(0, externalCriticStart) + sourceText.slice(parserStart);
}
sourceText = sourceText.replace(/^const GEMINI_MODEL.*\n/m, "");
sourceText = sourceText.replaceAll("1.3.6", "1.4.0");

const twoModelRiskSupport = [
  "function assessRisk(input, candidateAnswer) {",
  "  let score = 0;",
  "  const reasons = [];",
  "  const records = Array.isArray(input.records) ? input.records : [];",
  "  if (records.some((r) => String(r.sourceKind || '').toLowerCase() === 'draft')) { score += 2; reasons.push('draft 근거 포함'); }",
  "  if (records.some((r) => String(r.sourceKind || '').toLowerCase() === 'unlinked' || !r.fullText)) { score += 1; reasons.push('원문 미연결 근거 포함'); }",
  "  if (records.length >= 3) { score += 1; reasons.push('복수 근거 결합'); }",
  "  const instruction = String(input.userInstruction || '');",
  "  if (/\\d/.test(instruction) || /(통계|수치|비율|퍼센트|연도|공식)/.test(instruction)) { score += 1; reasons.push('수치·공식 사실 수정 가능성'); }",
  "  const completionWords = ['제작','완성','검증','측정','분석','구현','실험','입증','개발'];",
  "  if (completionWords.some((word) => instruction.includes(word))) { score += 1; reasons.push('완료·성과 표현 요청'); }",
  "  if (candidateAnswer) {",
  "    const corpus = [input.question?.text, input.question?.target, input.question?.method, input.currentAnswer, input.userInstruction, ...records.flatMap((r) => [r.summary, r.fullText, r.limits])].filter(Boolean).join('\\n');",
  "    const inputNumbers = new Set(corpus.match(/\\d+(?:[.,]\\d+)?%?/g) || []);",
  "    const outputNumbers = new Set(String(candidateAnswer).match(/\\d+(?:[.,]\\d+)?%?/g) || []);",
  "    const newNumbers = [...outputNumbers].filter((n) => !inputNumbers.has(n));",
  "    if (newNumbers.length) { score += 3; reasons.push('근거에 없는 새 수치: ' + newNumbers.slice(0,3).join(', ')); }",
  "    if (completionWords.some((word) => String(candidateAnswer).includes(word) && !corpus.includes(word))) { score += 2; reasons.push('근거보다 강한 완료·성과 표현'); }",
  "    const driverContext = /(기관사|운전|철도차량)/.test([input.question?.text, input.currentAnswer, input.userInstruction].filter(Boolean).join('\\n'));",
  "    const boundaryWords = ['수리','정비했다','정비를 수행','선로를 점검','시설을 점검','부품을 교체'];",
  "    if (driverContext && boundaryWords.some((word) => String(candidateAnswer).includes(word))) { score += 3; reasons.push('기관사 역할 경계 위험'); }",
  "    if (!looksComplete(candidateAnswer)) { score += 2; reasons.push('답안 문장 미완결 가능성'); }",
  "  }",
  "  return normalizeRisk(score, reasons);",
  "}",
  "",
  "function mergeRisk(a, b) {",
  "  const score = Math.max(Number(a?.score || 0), Number(b?.score || 0));",
  "  const reasons = [...new Set([...(a?.reasons || []), ...(b?.reasons || [])])];",
  "  return normalizeRisk(score, reasons);",
  "}",
  "",
  "function normalizeRisk(score, reasons) {",
  "  return { level: score >= 5 ? 'high' : score >= 2 ? 'medium' : 'low', score, reasons };",
  "}",
  "",
  "function looksComplete(text) {",
  "  const value = String(text || '').trim();",
  "  if (value.length < 12) return false;",
  "  if (/[.!?。！？][\\\"'”’)]?$/.test(value)) return true;",
  "  return /(습니다|입니다|했습니다|됩니다|생각합니다|느꼈습니다|배웠습니다|알게 되었습니다|있습니다)$/.test(value);",
  "}",
].join("\n");

if (!sourceText.includes("function assessRisk(")) sourceText += "\n\n" + twoModelRiskSupport;

const aiUiScript = fs.readFileSync(new URL("./ai-ui.js", import.meta.url), "utf8");
const appProxySupport = [
  "const UPSTREAM_INTERVIEW_APP = 'https://wsu-rail-interview-33.vercel.app/';",
  "const AI_UI_JS = " + JSON.stringify(aiUiScript) + ";",
  "",
  "async function serveInterviewApp(request) {",
  "  const upstream = await fetch(UPSTREAM_INTERVIEW_APP, { headers: { 'User-Agent': 'WSU-Interview-AI-Proxy/1.4' } });",
  "  if (!upstream.ok) return new Response('Upstream interview app unavailable', { status: 502 });",
  "  const html = await upstream.text();",
  "  const injected = html.includes('/ai-ui.js') ? html : html.replace('</body>', '<script src=/ai-ui.js></script></body>');",
  "  return new Response(injected, {",
  "    status: 200,",
  "    headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store, max-age=0', 'X-Content-Type-Options': 'nosniff' },",
  "  });",
  "}",
].join("\n");
sourceText += "\n\n" + appProxySupport;

const requiredRuntimeFunctions = ["normalizeRequest","assessRisk","mergeRisk","callGLM","callLlamaDirect","callLlamaVerifier","looksComplete","compact","handleOptions","json"];
for (const fn of requiredRuntimeFunctions) {
  const present = sourceText.includes("function " + fn + "(") || sourceText.includes("async function " + fn + "(");
  if (!present) throw new Error("required runtime function missing: " + fn);
}

if (/gemini|generativelanguage|GEMINI_API_KEY|ENABLE_GEMINI/i.test(sourceText)) {
  throw new Error("external critic code remains after v1.4.0 transformation");
}

const source = Buffer.from(sourceText, "utf8");
const hash = crypto.createHash("sha256").update(source).digest("hex");
fs.writeFileSync(new URL("./src/index.js", import.meta.url), source);
console.log(`Generated src/index.js v1.4.0 (${source.length} bytes, sha256 ${hash})`);
