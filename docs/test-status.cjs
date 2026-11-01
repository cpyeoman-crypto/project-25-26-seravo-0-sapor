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
console.log("Public schema: accepted valid rows; rejected private fields, injection and invalid metrics.");
