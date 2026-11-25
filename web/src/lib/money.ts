export type Money = { currency: string; amount: string };

export const money = ({ currency, amount }: Money) =>
  `${currency} ${Number(amount).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
