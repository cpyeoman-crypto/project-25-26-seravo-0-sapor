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
const event = {alias:"client-"+"a".repeat(20),kind:"uplink-drop",priority:5,age_min:12};
assert.equal(validate({...valid,events:[event]}).events[0], event);
assert.equal(validate(valid).events, undefined);
for (const patch of [{message:"raw alert"},{kind:"real-hostname"},{kind:"<img>"},{alias:"incident-"+"b".repeat(20)},
  {priority:0},{priority:"5"},{age_min:-1},{age_min:10081},{age_min:1.5},{time:"2026-01-01T00:00:00Z"}]) {
  assert.throws(() => validate({...valid,events:[{...event,...patch}]}));
}
assert.throws(() => validate({...valid,events:Array(51).fill(event)}));
console.log("Public schema: accepted valid rows; rejected private fields, injection and invalid metrics.");
