// Reads the PR state as JSON on stdin, prints the decision as JSON. Used by .github/workflows/factory-merge.yml.
import { decide } from "./auto-merge.js";

let input = "";
for await (const chunk of process.stdin) input += chunk;
console.log(JSON.stringify(decide(JSON.parse(input))));
