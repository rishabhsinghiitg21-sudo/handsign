import { describe, expect, it } from "vitest";
import { renameKey, renameWorkflow, uniqueName, workflowUsers } from "./configEdit";

const wf = (v: string) => ({ type: "workflow", value: v });
const make = () => ({
  poses: { fist: { action: wf("greet") }, shaka: { action: { type: "key", value: "esc" } } },
  sequences: { combo: { steps: ["fist"], action: wf("greet") } },
  voice_commands: { hello: { action: wf("greet") }, other: { action: wf("shot") } },
  expressions: { smile: { action: wf("greet") } },
  combined: [{ gesture: "point", action: wf("greet") }],
  workflows: {
    greet: { steps: [{ action: { type: "text", value: "hi" } }] },
    shot: { steps: [{ action: wf("greet") }] },
  },
});

describe("renameWorkflow", () => {
  it("repoints every binding, nested workflow steps included, and keeps order", () => {
    const cfg = make();
    renameWorkflow(cfg, "greet", "welcome");
    expect(Object.keys(cfg.workflows)).toEqual(["welcome", "shot"]);
    expect(workflowUsers(cfg, "greet")).toEqual([]);
    expect(cfg.poses.fist.action.value).toBe("welcome");
    expect(cfg.sequences.combo.action.value).toBe("welcome");
    expect(cfg.voice_commands.hello.action.value).toBe("welcome");
    expect(cfg.expressions.smile.action.value).toBe("welcome");
    expect(cfg.combined[0].action.value).toBe("welcome");
    expect(cfg.workflows.shot.steps[0].action.value).toBe("welcome");
  });

  it("leaves other workflows and non-workflow actions alone", () => {
    const cfg = make();
    renameWorkflow(cfg, "greet", "welcome");
    expect(cfg.voice_commands.other.action.value).toBe("shot");
    expect(cfg.poses.shaka.action).toEqual({ type: "key", value: "esc" });
  });
});

describe("workflowUsers", () => {
  it("lists where a workflow is used", () => {
    expect(workflowUsers(make(), "greet")).toEqual([
      "poses: fist", "sequences: combo", "voice commands: hello",
      "expressions: smile", "combined #1", "workflow shot, step 1",
    ]);
    expect(workflowUsers(make(), "missing")).toEqual([]);
  });
});

describe("helpers", () => {
  it("renameKey keeps position", () => {
    expect(Object.keys(renameKey({ a: 1, b: 2, c: 3 }, "b", "x"))).toEqual(["a", "x", "c"]);
  });
  it("uniqueName never collides", () => {
    expect(uniqueName("workflow", ["workflow", "workflow_2"])).toBe("workflow_3");
  });
});
