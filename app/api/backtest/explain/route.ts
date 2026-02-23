import { NextResponse } from 'next/server';
import { exec } from 'child_process';
import util from 'util';

const execPromise = util.promisify(exec);

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

    const command = `PYTHONPATH=.:backend python backend/ai/xai_engine.py ${symbol} ${date}`;
    
    // Set a reasonable timeout since SHAP might take a few seconds
    const { stdout, stderr } = await execPromise(command, { timeout: 30000 });
    
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
    return NextResponse.json({ error: 'Internal server error running XAI' }, { status: 500 });
  }
}
