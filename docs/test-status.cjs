const assert = require("node:assert/strict");
const {validate} = require("./status.js");
const valid = {schema_version:1,nodes:[{alias:"client-"+"a".repeat(20),status:"online",cpu_pct:25}],
  incidents:[{alias:"incident-"+"b".repeat(20),status:"pending_review",priority:4}]};
assert.equal(validate(valid), valid);
for (const patch of [{ip:"192.0.2.1"},{password:"synthetic"},{name:"synthetic-owner"},{cpu_pct:NaN},
  {alias:"<script>"},{status:"anything"},{cpu_pct:true}]) {
  assert.throws(() => validate({...valid,nodes:[{...valid.nodes[0],...patch}]}));
}
assert.throws(() => validate({...valid,incidents:[{...valid.incidents[0],message:"raw alert"}]}));
assert.throws(() => validate({...valid,secret:"synthetic"}));
const event = {role:"ap 2", kind:"connect", priority:3, age_min:10,
  title:"fleet · Standard WLAN Connect",
  message:"## 🟢 CLIENT CONNECT\n\n[WLAN Connect] Name: iot plug | IP: 192.0.2.7 | VLAN: X\n\n- **MAC** `02:00:00:00:00:01`\n\n*fleet · hub · X*"};
assert.equal(validate({...valid,events:[event]}).events[0], event);
assert.equal(validate(valid).events, undefined);
for (const patch of [{title:"farm site · WLAN"},{message:"IP: 10.1.2.3"},{message:"MAC a4:cf:12:34:56:78"},
  {role:"RealHostName"},{role:""},{kind:"real-hostname"},{title:"line\nbreak"},{title:""},
  {message:"x".repeat(1501)},{priority:0},{priority:"5"},{age_min:-1},{age_min:10081},{age_min:1.5},
  {alias:"client-"+"a".repeat(20)}]) {
  assert.throws(() => validate({...valid,events:[{...event,...patch}]}));
}
assert.throws(() => validate({...valid,events:Array(51).fill(event)}));
console.log("Public schema: accepted valid rows; rejected private fields, injection and invalid metrics.");
