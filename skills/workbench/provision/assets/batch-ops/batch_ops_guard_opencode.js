// First Four Hours batch-ops guard for OpenCode, copied into the plugins folder by Provision.
// While batch-ops is connected, it refuses the primary agent's native file and shell tools inside
// the project, naming the batch-ops tool to use. Subagents, files outside the project, background
// shell commands, and the plan agent's shell keep native tools, and anything the guard cannot read
// or recognize allows the call, so it never strands an agent that has no batch-ops tools.
import path from "node:path"

const USE = {
  read: "batch-ops_batch_read",
  glob: "batch-ops_batch_read",
  grep: "batch-ops_batch_read",
  edit: "batch-ops_batch_edit",
  write: "batch-ops_batch_edit",
  patch: "batch-ops_batch_edit",
  shell: "batch-ops_batch_run",
}
const PATCH = /^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$/gm

function inside(root, target) {
  const rel = path.relative(root, path.resolve(root, target))
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel))
}

function targets(tool, input) {
  if (tool === "patch") return [...String(input.patchText ?? "").matchAll(PATCH)].map((match) => match[1].trim())
  return [input.path ?? input.filePath].filter((value) => typeof value === "string" && value !== "")
}

export default {
  id: "ffh-batch-ops-guard",
  async setup(ctx) {
    await ctx.tool.hook("execute.before", async (event) => {
      const use = USE[event.tool]
      if (!use) return
      let refuse = false
      try {
        const input = event.input ?? {}
        if (event.tool === "shell" && (input.background || event.agent === "plan")) return
        const root = ctx.location.project?.directory ?? ctx.location.directory
        const paths = targets(event.tool, input)
        if (paths.length && !paths.some((target) => inside(root, target))) return
        const agent = await ctx.agent.get({ agentID: event.agent })
        if (agent?.data?.mode === "subagent") return
        const servers = await ctx.mcp.list({ location: { directory: ctx.location.directory } })
        refuse = (servers?.data ?? []).some((server) => server.name === "batch-ops" && server.status?.status === "connected")
      } catch {
        return
      }
      if (refuse) {
        throw new Error(
          `batch-ops is connected, so ${event.tool} inside this project goes through ${use}. ` +
            "If batch-ops calls fail, tell the user rather than retrying natively.",
        )
      }
    })
  },
}
