import { describe, expect, test } from "bun:test";
import { localSTTSetup } from "./stt-setup";

const untouched = { endpoint: false, serverType: false };

describe("localSTTSetup", () => {
  test("sends the loaded endpoint and dialect", () => {
    expect(localSTTSetup({
      endpoint: " http://localhost:8000/v1 ",
      serverType: "openai_compatible",
      loaded: true,
      touched: untouched,
    })).toEqual({ endpoint: "http://localhost:8000/v1", server_type: "openai_compatible" });
  });

  test("sends nothing when the stored config was not read and nothing was edited", () => {
    expect(localSTTSetup({
      endpoint: "http://localhost:8080",
      serverType: "whisper_cpp",
      loaded: false,
      touched: untouched,
    })).toBeUndefined();
  });

  test("sends only the edited dialect when the stored config was not read", () => {
    expect(localSTTSetup({
      endpoint: "http://localhost:8080",
      serverType: "openai_compatible",
      loaded: false,
      touched: { endpoint: false, serverType: true },
    })).toEqual({ server_type: "openai_compatible" });
  });

  test("sends only the edited endpoint when the stored config was not read", () => {
    expect(localSTTSetup({
      endpoint: "http://speech:9000",
      serverType: "whisper_cpp",
      loaded: false,
      touched: { endpoint: true, serverType: false },
    })).toEqual({ endpoint: "http://speech:9000" });
  });

  test("never sends a blank endpoint", () => {
    expect(localSTTSetup({
      endpoint: "  ",
      serverType: "whisper_cpp",
      loaded: true,
      touched: { endpoint: true, serverType: false },
    })).toEqual({ server_type: "whisper_cpp" });
  });
});
