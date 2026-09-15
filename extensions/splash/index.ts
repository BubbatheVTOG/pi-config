import { readFileSync } from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const ART_PATH = new URL("./art.txt", import.meta.url);
const ART_WIDTH = 80;
const ART_HEIGHT = 26;
const DOCK_ROWS = 6;
const COLOR = "\x1b[38;2;255;255;255m";
const CAPTION_COLOR = "\x1b[38;2;180;180;180m";
const RESET = "\x1b[39m";
const FALLBACK = "∏";
const CAPTION = "An agentic coding harness configuration curated by Bubba";
const CAPTION_ROWS = 2;
const SPLASH_HEIGHT = ART_HEIGHT + CAPTION_ROWS;
const VALID_ART_CHARACTERS = new Set([" ", "█", "═", "║", "╔", "╗", "╚", "╝"]);

type CloseSplash = () => void;

function warn(message: string, detail?: string): void {
  process.stderr.write(
    `[pi-splash] ${message}${detail ? `: ${detail}` : ""}\n`,
  );
}

function describeError(error: Error | string): string {
  return error instanceof Error ? error.message : error;
}

function loadArt(): string[] {
  const lines = readFileSync(ART_PATH, "utf8").replace(/\n$/, "").split("\n");
  if (lines.length !== ART_HEIGHT) {
    throw new Error(`expected ${ART_HEIGHT} lines, got ${lines.length}`);
  }

  for (const [lineIndex, line] of lines.entries()) {
    const characters = Array.from(line);
    if (
      characters.length !== ART_WIDTH ||
      characters.some((character) => !VALID_ART_CHARACTERS.has(character))
    ) {
      throw new Error(
        `line ${lineIndex + 1} is not ${ART_WIDTH} validated single-cell characters`,
      );
    }
  }

  return lines;
}

function colored(line: string): string {
  return `${COLOR}${line}${RESET}`;
}

function centerLine(text: string, width: number): string {
  if (text.length >= width) return text.slice(0, width);
  const left = Math.floor((width - text.length) / 2);
  return `${" ".repeat(left)}${text}${" ".repeat(width - text.length - left)}`;
}

function captionLines(): string[] {
  return [
    " ".repeat(ART_WIDTH),
    `${CAPTION_COLOR}${centerLine(CAPTION, ART_WIDTH)}${RESET}`,
  ];
}

export default function (pi: ExtensionAPI): void {
  let closeSplash: CloseSplash | undefined;
  let activeTui: { terminal: { columns: number; rows: number } } | undefined;

  pi.on("session_start", (event, ctx) => {
    if (ctx.mode !== "tui" || !ctx.hasUI) return;

    // Drop the built-in startup header so boot is splash + editor + footer.
    ctx.ui.setHeader(() => ({
      render(): string[] {
        return [];
      },
      invalidate(): void {},
    }));

    if (event.reason !== "startup") return;

    let art: string[];
    try {
      art = loadArt();
    } catch (error) {
      warn(
        "unable to load or validate splash art; continuing startup",
        describeError(error instanceof Error ? error : String(error)),
      );
      return;
    }

    let closed = false;
    let doneSplash: (() => void) | undefined;
    const close = (): void => {
      if (closed) return;
      closed = true;
      closeSplash = undefined;
      doneSplash?.();
    };
    closeSplash = close;

    void ctx.ui
      .custom<void>(
        (tui, _theme, _keybindings, done) => {
          activeTui = tui;
          doneSplash = (): void => done();
          // The session can close before an asynchronous UI factory is mounted.
          if (closed) doneSplash();

          return {
            render(width: number): string[] {
              if (width <= 0) return [];
              const terminalWidth = tui.terminal.columns;
              const terminalHeight = tui.terminal.rows;
              if (
                terminalWidth < ART_WIDTH ||
                terminalHeight < SPLASH_HEIGHT + DOCK_ROWS ||
                width < ART_WIDTH
              ) {
                return [colored(FALLBACK)];
              }
              return [...art.map(colored), ...captionLines()];
            },
            invalidate(): void {},
          };
        },
        {
          overlay: true,
          overlayOptions: () => {
            const wideEnough =
              (activeTui?.terminal.columns ?? 0) >= ART_WIDTH &&
              (activeTui?.terminal.rows ?? 0) >= SPLASH_HEIGHT + DOCK_ROWS;
            return {
              anchor: "center",
              width: wideEnough ? ART_WIDTH : 1,
              margin: { bottom: DOCK_ROWS },
              nonCapturing: true,
            };
          },
        },
      )
      .catch((error) =>
        warn(
          "splash UI failed; continuing startup",
          describeError(error instanceof Error ? error : String(error)),
        ),
      );
  });

  pi.on("before_agent_start", () => {
    closeSplash?.();
  });

  pi.on("session_shutdown", () => {
    closeSplash?.();
  });
}
