export type ImportedFormField = { key: string; label: string; required: boolean; sequence_no: number };

export function parseFormFieldLines(value: string): ImportedFormField[] {
  return value.split("\n").map((line) => line.trim()).filter(Boolean).map((line, index) => {
    const [key, label, required] = line.split("|").map((part) => part.trim());
    return {
      key: key || `field_${index + 1}`,
      label: label || key || `Field ${index + 1}`,
      required: required.toLowerCase() === "true",
      sequence_no: index + 1,
    };
  });
}

export function parseAssessmentQuestionLines(value: string) {
  return value.split("\n").map((line) => line.trim()).filter(Boolean).map((line, index) => {
    const [sequence, question_text, response_type, mandatory, marks] = line.split("|").map((item) => item.trim());
    return {
      sequence_no: Number(sequence || index + 1),
      question_text,
      response_type: response_type || "TEXT",
      mandatory: mandatory.toLowerCase() === "true",
      marks: Number(marks || 0),
      answer_options: [] as string[],
      evaluation_rule: {} as Record<string, unknown>,
    };
  });
}

export function parseSignatoryLines(value: string): Array<{ name: string; title: string }> {
  return value.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
    const [name, title] = line.split("|").map((part) => part.trim());
    return { name, title: title || "Authorised signatory" };
  });
}
