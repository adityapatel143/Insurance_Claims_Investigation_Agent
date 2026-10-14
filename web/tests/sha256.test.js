import assert from "node:assert/strict";
import { createHash, createHmac, randomBytes } from "node:crypto";
import { test } from "node:test";

import { hmacSha256, sha256, toHex, utf8 } from "../js/sha256.js";

test("sha256 matches node:crypto across block boundaries", () => {
  for (const length of [0, 1, 55, 56, 63, 64, 65, 119, 120, 1000, 70000]) {
    const data = randomBytes(length);
    assert.equal(toHex(sha256(new Uint8Array(data))), createHash("sha256").update(data).digest("hex"), `length ${length}`);
  }
});

test("sha256 of known vector", () => {
  assert.equal(toHex(sha256(utf8("abc"))), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
});

test("hmacSha256 matches node:crypto for short and long keys", () => {
  for (const keyLength of [0, 16, 64, 65, 200]) {
    const key = randomBytes(keyLength);
    const message = randomBytes(300);
    const expected = createHmac("sha256", key).update(message).digest("hex");
    assert.equal(toHex(hmacSha256(new Uint8Array(key), new Uint8Array(message))), expected, `key ${keyLength}`);
  }
});
