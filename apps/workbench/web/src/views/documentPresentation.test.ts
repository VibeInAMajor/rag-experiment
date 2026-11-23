import { describe, expect, it } from "vitest";
import {
  boundedDocumentText,
  documentMetadataText,
  documentPage,
} from "./documentPresentation";

describe("document presentation boundaries", () => {
  it("keeps absent page provenance unavailable", () => {
    expect(documentPage(null)).toBe("Unavailable");
    expect(documentPage(undefined)).toBe("Unavailable");
    expect(documentPage(3)).toBe("3");
  });
  it("bounds untrusted metadata and marks truncation", () => {
    const result = documentMetadataText({
      original_excerpt: "x".repeat(10000),
    });
    expect(result.length).toBeLessThan(6100);
    expect(result).toContain("Metadata display truncated");
    expect(documentMetadataText(null)).toBe("Not reported");
  });
  it("retains document text as inert text without interpreting markup", () => {
    expect(boundedDocumentText('<script>alert("test")</script>')).toEqual({
      text: '<script>alert("test")</script>',
      truncated: false,
    });
  });
});
