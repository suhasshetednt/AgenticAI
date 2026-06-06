// Pure marker parser shared by the dashboard (browser) and its node test.
// Returns one of: {kind:'stage',name,status} | {kind:'artifact',artifactKind,value}
//               | {kind:'approve',approveKind,detail} | {kind:'done'} | {kind:'log',text}
function parseMarker(line) {
  const s = String(line).trim();
  let m;
  if ((m = s.match(/^::STAGE\s+(\w+)\s+(start|done|fail)::$/))) {
    return { kind: "stage", name: m[1], status: m[2] };
  }
  if ((m = s.match(/^::ARTIFACT\s+(\w+)=(.*)::$/))) {
    return { kind: "artifact", artifactKind: m[1], value: m[2] };
  }
  if ((m = s.match(/^::APPROVE\s+(\w+)=(.*)::$/))) {
    return { kind: "approve", approveKind: m[1], detail: m[2] };
  }
  if (s === "::DONE::") {
    return { kind: "done" };
  }
  return { kind: "log", text: line };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { parseMarker };
}
