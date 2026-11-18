import { exercise, setup, thresholds } from "./common.js";
export { setup, handleSummary } from "./common.js";
export const options = { stages: [{ duration: "30s", target: 10 }, { duration: "1m", target: 50 }, { duration: "30s", target: 0 }], thresholds };
export default exercise;
