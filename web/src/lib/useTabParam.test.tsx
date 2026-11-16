import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useTabParam } from "./useTabParam";

const replace = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/page",
  useSearchParams: () => new URLSearchParams(search),
}));

beforeEach(() => {
  replace.mockReset();
  search = "";
});

describe("useTabParam", () => {
  it("is the first value when the address names none", () => {
    const { result } = renderHook(() => useTabParam(["a", "b"]));
    expect(result.current[0]).toBe("a");
  });

  it("is the one named in the address", () => {
    search = "tab=b";
    expect(renderHook(() => useTabParam(["a", "b"])).result.current[0]).toBe("b");
  });

  it.each(["nope", ""])("falls back to the first for %j", (value) => {
    search = `tab=${value}`;
    expect(renderHook(() => useTabParam(["a", "b"])).result.current[0]).toBe("a");
  });

  it("puts the choice into the address and keeps the other parts", () => {
    search = "ids=k1,k2";
    const { result } = renderHook(() => useTabParam(["a", "b"], "view"));
    result.current[1]("b");
    expect(replace).toHaveBeenCalledWith("/page?ids=k1%2Ck2&view=b", { scroll: false });
  });

  it("replaces the same part of the address when it is already there", () => {
    search = "view=a&x=1";
    const { result } = renderHook(() => useTabParam(["a", "b"], "view"));
    result.current[1]("b");
    expect(replace).toHaveBeenCalledWith("/page?view=b&x=1", { scroll: false });
  });
});
