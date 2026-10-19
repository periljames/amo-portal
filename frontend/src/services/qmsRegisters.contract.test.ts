import { beforeEach, expect, it, vi } from "vitest";
vi.mock("./apiClient",()=>({apiRequest:vi.fn(),qmsPath:(amo:string,path:string)=>`/api/maintenance/${amo}/quality${path}`}));
import { apiRequest } from "./apiClient";
import { qmsGetAuditRegisterPage,qmsGetCarRegisterPage } from "./qmsRegisters";
beforeEach(()=>vi.clearAllMocks());
it("rejects a successful generic response instead of rendering a broken finding page",async()=>{
  vi.mocked(apiRequest).mockResolvedValue({items:[],total:0});
  await expect(qmsGetAuditRegisterPage({amoCode:"test",findingId:"finding"})).rejects.toThrow("incomplete record");
});
it("preserves the authoritative finding register result",async()=>{
  const page={rows:[],total:0};vi.mocked(apiRequest).mockResolvedValue(page);
  await expect(qmsGetAuditRegisterPage({amoCode:"test"})).resolves.toBe(page);
});
it("does not invent zero CAR summary counts from an incomplete response",async()=>{
  vi.mocked(apiRequest).mockResolvedValue({items:[],total:0});
  await expect(qmsGetCarRegisterPage({amoCode:"test"})).rejects.toThrow("incomplete record");
});
it("preserves the complete CAR register result",async()=>{
  const page={items:[],total:0,summary:{total:0,open:0,overdue:0,in_review:0}};vi.mocked(apiRequest).mockResolvedValue(page);
  await expect(qmsGetCarRegisterPage({amoCode:"test"})).resolves.toBe(page);
});
