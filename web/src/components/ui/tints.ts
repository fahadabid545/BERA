/** The pastel card colours of the panel's summary, project, plan and empty-state cards. They
 * take turns in this order, so neighbours differ and no colour means anything on its own. */
export type Tint = "lime" | "lilac" | "peach" | "sky" | "pink";

const TINT_ORDER: readonly Tint[] = ["lime", "lilac", "peach", "sky", "pink"];

export const tintAt = (position: number): Tint => TINT_ORDER[position % TINT_ORDER.length];
