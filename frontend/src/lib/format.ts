const DECIMAL = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/;

export function isDecimalString(value: string): boolean {
  return DECIMAL.test(value);
}

/** Move the decimal point two places. This is a display conversion of a stored share. */
export function shareToPercentText(share: string): string {
  if (!isDecimalString(share)) {
    throw new Error("Coverage must be a decimal string.");
  }
  const negative = share.startsWith("-");
  const unsigned = negative ? share.slice(1) : share;
  const [whole, fraction = ""] = unsigned.split(".");
  const digits = `${whole}${fraction}`;
  const point = whole.length + 2;
  const padded = digits.padEnd(point, "0");
  const left = padded.slice(0, point).replace(/^0+(?=\d)/, "") || "0";
  const right = padded.slice(point).replace(/0+$/, "");
  const body = right.length > 0 ? `${left}.${right}` : left;
  if (negative && body !== "0") {
    return `-${body}`;
  }
  return body;
}

export function signedIntegerText(value: number): string {
  if (!Number.isInteger(value)) {
    throw new Error("Threshold must be an integer.");
  }
  if (value > 0) {
    return `+${value}`;
  }
  return String(value);
}
