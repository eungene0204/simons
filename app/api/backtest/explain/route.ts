import { NextResponse } from 'next/server';
import { exec } from 'child_process';
import util from 'util';

const execPromise = util.promisify(exec);
const XAI_TIMEOUT_MS = 180000;
const XAI_CACHE_DIR = "/tmp/simons-xai-cache";

function isMpsRuntimeFailure(message: string) {
  const lowered = message.toLowerCase();
  return (
    lowered.includes("metalperformanceshaders") ||
    lowered.includes("mpsndarray") ||
    lowered.includes("ndarray dimension length > int_max") ||
    lowered.includes("mps")
  );
}

async function runXaiCommand(symbol: string, date: string, forceCpu = false) {
  const command = `python backend/ai/xai_engine.py ${symbol} ${date}`;
  return execPromise(command, {
    timeout: XAI_TIMEOUT_MS,
    env: {
      ...process.env,
      PYTHONPATH: ".:backend",
      MPLCONFIGDIR: `${XAI_CACHE_DIR}/mpl`,
      XDG_CACHE_HOME: `${XAI_CACHE_DIR}/xdg`,
      XAI_FORCE_CPU: forceCpu ? "1" : "0",
    },
  });
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { symbol, date } = body;

    if (!symbol || !date) {
      return NextResponse.json({ error: 'Missing symbol or date parameters' }, { status: 400 });
    }

    // Input validation to prevent command injection
    if (!/^[a-zA-Z0-9.]+$/.test(symbol) || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return NextResponse.json({ error: 'Invalid parameters format' }, { status: 400 });
    }

    let stdout: string;
    let stderr: string;

    try {
      ({ stdout, stderr } = await runXaiCommand(symbol, date));
    } catch (error) {
      const execError = error as NodeJS.ErrnoException & {
        stdout?: string;
        stderr?: string;
      };

      const errorText = [execError.stderr, execError.stdout, execError.message]
        .filter(Boolean)
        .join("\n");

      if (isMpsRuntimeFailure(errorText)) {
        ({ stdout, stderr } = await runXaiCommand(symbol, date, true));
      } else {
        throw error;
      }
    }
    
    // Parse the JSON output from the python script
    try {
      const result = JSON.parse(stdout.trim());
      
      if (result.error) {
        return NextResponse.json({ error: result.error, details: result.traceback }, { status: 500 });
      }

      return NextResponse.json(result);
    } catch (parseError) {
      console.error("Failed to parse XAI python output:", stdout);
      console.error("stderr:", stderr);
      return NextResponse.json({ error: 'Failed to parse python engine output' }, { status: 500 });
    }
    
  } catch (error) {
    console.error("Error running XAI engine:", error);
    const execError = error as NodeJS.ErrnoException & {
      stdout?: string;
      stderr?: string;
      killed?: boolean;
      signal?: string;
      code?: string | number;
    };

    const stderr = execError.stderr?.trim();
    const stdout = execError.stdout?.trim();
    const isTimeout = execError.killed || execError.signal === "SIGTERM";

    return NextResponse.json(
      {
        error: isTimeout
          ? `XAI analysis timed out after ${Math.round(XAI_TIMEOUT_MS / 1000)} seconds`
          : stderr || stdout || execError.message || 'Internal server error running XAI',
      },
      { status: 500 }
    );
  }
}
