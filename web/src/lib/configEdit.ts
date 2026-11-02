// Helpers for editing the gestures.json object in the console.

/** Rename a key but keep its position, so rows don't jump around while editing. */
export function renameKey<T>(obj: Record<string, T>, from: string, to: string): Record<string, T> {
  if (from === to) return obj;
  const out: Record<string, T> = {};
  for (const [k, v] of Object.entries(obj)) out[k === from ? to : k] = v;
  return out;
}

/** `base`, or `base_2`, `base_3`… if that name is already taken (never overwrites). */
export function uniqueName(base: string, taken: string[], sep = "_"): string {
  if (!taken.includes(base)) return base;
  let n = 2;
  while (taken.includes(`${base}${sep}${n}`)) n++;
  return `${base}${sep}${n}`;
}

type Cfg = Record<string, any>;

/** Every action object in the config, with a label saying where it lives. */
function* actionSlots(cfg: Cfg): Generator<{ where: string; action: any }> {
  for (const section of ["poses", "sequences", "voice_commands", "expressions"]) {
    for (const [k, spec] of Object.entries<any>(cfg[section] ?? {}))
      if (spec?.action) yield { where: `${section.replace("_", " ")}: ${k}`, action: spec.action };
  }
  for (const [i, c] of (cfg.combined ?? []).entries())
    if (c?.action) yield { where: `combined #${i + 1}`, action: c.action };
  for (const [w, wf] of Object.entries<any>(cfg.workflows ?? {}))
    for (const [i, st] of (wf?.steps ?? []).entries())
      if (st?.action) yield { where: `workflow ${w}, step ${i + 1}`, action: st.action };
}

/** Where the workflow `name` is used by a binding or by another workflow. */
export function workflowUsers(cfg: Cfg, name: string): string[] {
  return [...actionSlots(cfg)]
    .filter((s) => s.action.type === "workflow" && s.action.value === name)
    .map((s) => s.where);
}

/** Rename workflow `from` to `to` and repoint every binding that used it. Mutates `cfg`. */
export function renameWorkflow(cfg: Cfg, from: string, to: string): void {
  for (const s of actionSlots(cfg))
    if (s.action.type === "workflow" && s.action.value === from) s.action.value = to;
  cfg.workflows = renameKey(cfg.workflows ?? {}, from, to);
}
