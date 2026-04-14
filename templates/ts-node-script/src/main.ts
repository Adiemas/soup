#!/usr/bin/env tsx
/**
 * Entry point for the script. Parses argv into a typed options object
 * (typer-ish — explicit, validated, help-on-bad-input), dispatches the
 * requested subcommand, exits 0/nonzero.
 *
 * Intended invocation: `tsx src/main.ts <subcommand> [--flag value]`
 *
 * Keep this file thin. Subcommands live alongside in src/*.ts so each
 * can be tested without booting the argv parser.
 */

import { z } from "zod";
import { fetchAndSummarize } from "./adapter.js";

const SUBCOMMANDS = ["run", "dry-run", "help"] as const;
type Subcommand = (typeof SUBCOMMANDS)[number];

const OptionsSchema = z.object({
  subcommand: z.enum(SUBCOMMANDS),
  source: z.string().min(1).default("local"),
  limit: z.coerce.number().int().positive().max(10_000).default(10),
  verbose: z.boolean().default(false),
});
type Options = z.infer<typeof OptionsSchema>;

function parseArgv(argv: ReadonlyArray<string>): Options {
  // argv[0] is the subcommand; remaining are --flag=value or --flag value.
  const [subcommandRaw, ...rest] = argv;
  const flags: Record<string, string | boolean> = {};
  for (let i = 0; i < rest.length; i += 1) {
    const tok = rest[i];
    if (!tok || !tok.startsWith("--")) continue;
    const key = tok.slice(2);
    if (key.includes("=")) {
      const eq = key.indexOf("=");
      flags[key.slice(0, eq)] = key.slice(eq + 1);
    } else {
      const next = rest[i + 1];
      if (next && !next.startsWith("--")) {
        flags[key] = next;
        i += 1;
      } else {
        flags[key] = true;
      }
    }
  }
  return OptionsSchema.parse({
    subcommand: (subcommandRaw as Subcommand | undefined) ?? "help",
    ...flags,
  });
}

function usage(): string {
  return [
    "usage: tsx src/main.ts <subcommand> [--source <id>] [--limit N] [--verbose]",
    "",
    "subcommands:",
    "  run        fetch and deliver results",
    "  dry-run    fetch + print; do not deliver",
    "  help       this message",
  ].join("\n");
}

async function main(argv: ReadonlyArray<string>): Promise<number> {
  let opts: Options;
  try {
    opts = parseArgv(argv);
  } catch (err) {
    process.stderr.write(`argv parse failed: ${String(err)}\n${usage()}\n`);
    return 2;
  }

  if (opts.subcommand === "help") {
    process.stdout.write(`${usage()}\n`);
    return 0;
  }

  const result = await fetchAndSummarize({
    source: opts.source,
    limit: opts.limit,
  });

  if (opts.verbose) {
    process.stdout.write(JSON.stringify(result, null, 2) + "\n");
  } else {
    process.stdout.write(`fetched=${result.items.length} source=${opts.source}\n`);
  }

  if (opts.subcommand === "dry-run") {
    process.stdout.write("(dry-run; nothing delivered)\n");
  }

  return 0;
}

// Only auto-run when invoked directly (not when imported under vitest).
if (import.meta.url === `file://${process.argv[1]}`) {
  main(process.argv.slice(2)).then(
    (code) => process.exit(code),
    (err) => {
      process.stderr.write(`fatal: ${String(err)}\n`);
      process.exit(1);
    }
  );
}

export { main, parseArgv };
