import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Pagination from "./Pagination";
import { pageNumbers } from "./paginationModel";

describe("scalable pagination",()=>{
 it("keeps first, neighbours and last accessible for large populations",()=>{expect(pageNumbers(500,1000)).toEqual([1,"gap-499",499,500,501,"gap-1000",1000]);});
 it("handles short registers without phantom pages",()=>{expect(pageNumbers(1,1)).toEqual([1]);expect(pageNumbers(2,3)).toEqual([1,2,3]);});
 it("does not invent a last page for continuation-only sources",()=>{expect(pageNumbers(5,undefined,true)).toEqual([1,"gap-4",4,5,6]);});
 it("supports direct jumps and announces the current page",()=>{
  const html=renderToStaticMarkup(<Pagination label="Findings" page={5} pageSize={25} total={2500} visibleCount={25} onPageChange={()=>{}} />);
  expect(html).toContain("Page 5 of 100");expect(html).toContain('aria-current="page"');expect(html).toContain('aria-label="Findings page number"');expect(html).toContain('aria-label="Last page"');expect(html).toContain("101–125 of 2,500");
 });
 it("keeps navigation usable during background refresh",()=>{
  const html=renderToStaticMarkup(<Pagination label="Findings" page={5} pageSize={25} total={2500} visibleCount={25} busy onPageChange={()=>{}} />);
  expect(html).toContain('aria-busy="true"');expect(html).not.toContain('disabled=""');
 });
});
