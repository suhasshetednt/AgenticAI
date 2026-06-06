const assert = require("assert");
const { parseMarker } = require("../docs/dashboard_parser.js");

assert.deepStrictEqual(parseMarker("::STAGE doc start::"),
  { kind: "stage", name: "doc", status: "start" });
assert.deepStrictEqual(parseMarker("::ARTIFACT docx=C:/x/ADL-1.docx::"),
  { kind: "artifact", artifactKind: "docx", value: "C:/x/ADL-1.docx" });
assert.deepStrictEqual(parseMarker("::APPROVE dremio=ADL-1: hi::"),
  { kind: "approve", approveKind: "dremio", detail: "ADL-1: hi" });
assert.deepStrictEqual(parseMarker("::DONE::"), { kind: "done" });
assert.deepStrictEqual(parseMarker("  Fetching ADL-1 ..."),
  { kind: "log", text: "  Fetching ADL-1 ..." });

console.log("ok - dashboard_parser");
