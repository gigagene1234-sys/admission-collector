import baseWorker from "./index.js";
import { handleCompetitionRequest, runCompetitionScheduled } from "./competition_v2.js";

export default {
  async fetch(request, env, ctx) {
    const competitionResponse = await handleCompetitionRequest(request, env, ctx);
    if (competitionResponse) return competitionResponse;
    return baseWorker.fetch(request, env, ctx);
  },

  async queue(batch, env, ctx) {
    return baseWorker.queue(batch, env, ctx);
  },

  async scheduled(event, env, ctx) {
    const scheduledTime = Number(event?.scheduledTime || Date.now());
    const minute = new Date(scheduledTime).getUTCMinutes();
    ctx.waitUntil(runCompetitionScheduled(env, scheduledTime));
    if (minute % 5 === 0) {
      ctx.waitUntil(Promise.resolve(baseWorker.scheduled(event, env, ctx)));
    }
  },
};
