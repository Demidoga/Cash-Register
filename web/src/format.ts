export function rupees(n: number): string {
  const sign = n < 0 ? "−" : "";
  return `${sign}Rs ${Math.abs(n).toLocaleString("en-PK")}`;
}

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function firstOfMonth(): string {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
}

export function lastOfMonth(): string {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth() + 1, 0).toISOString().slice(0, 10);
}
