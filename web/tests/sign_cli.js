// Prints the headers produced by signRequest for a JSON request read from stdin (used by pytest).
import { signRequest } from "../js/sigv4.js";

let input = "";
process.stdin.setEncoding("utf8");
for await (const chunk of process.stdin) input += chunk;
process.stdout.write(JSON.stringify(signRequest(JSON.parse(input))));
