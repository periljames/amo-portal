import { expect, it } from "vitest";
import { extractWordChecklistTables } from "./qmsWordChecklistImport";
const cells = (values: string[]) => values.map(text => ({ text }));
it("excludes cover tables, keeps short questions and spaced references, and reads each source header", () => {
  const items = extractWordChecklistTables([
    [cells(["Post holders", "Name", "Contact"]), cells(["", "Airframes", ""])],
    [cells(["1.0", "MANAGEMENT", "YES", "NO", "N/A"]), cells(["1. 1", "Valid?", "", "", ""]), cells(["1.2", "Check records\nIncluding expiry dates", "", "", ""]), [{text:"Remarks:",span:5}]],
    [cells(["2.0", "QUALITY MANAGEMENT", "YES", "N O", "N/A"]), cells(["2.1", "Is the system independent?", "", "", ""])],
  ]);
  expect(items.map(item=>item.checklist_ref)).toEqual(["1.1", "1.2", "2.1"]);
  expect(items[0].prompt).toBe("Valid?");
  expect(items[1].prompt).toContain("\nIncluding expiry dates");
  expect(items[2].section).toBe("QUALITY MANAGEMENT");
  expect(items[2].response_options?.map(option=>option.value)).toEqual(["YES", "NO", "N/A"]);
});
it("retains workshop subheadings without creating extra questions", () => {
  const items = extractWordChecklistTables([[cells(["10.0","WORKSHOP","YES","NO","N/A"]),cells(["BATTERY WORKSHOP","","",""]),cells(["10.1","Are staff trained?","","",""])]]);
  expect(items).toHaveLength(1);
  expect(items[0].section).toBe("WORKSHOP / BATTERY WORKSHOP");
});
it("does not infer unknown assessment meanings or treat cover YES/NO cells as questions", () => {
  expect(extractWordChecklistTables([[cells(["Approvals held","Valid","Expiry","Remarks"]), cells(["","YES","NO","",""])], [cells(["1.0","Assessment","GOOD","BAD","MAYBE"]), cells(["1.1","Question","","",""]) ]])).toEqual([]);
});
