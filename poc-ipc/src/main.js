/**
 * Ramesh Saini v7.1 - PoC 1: Electron Main Process
 * 
 * This module demonstrates the Electron + Embedded Python IPC architecture.
 * In production, the Python subprocess would be bundled inside the Electron app.
 * Here we spawn it as a child process and communicate via stdio with length-prefixed JSON.
 */
const { app } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const net = require('net');

class RameshIPCBridge {
  constructor(pythonScript = null) {
    this.pythonProcess = null;
    this.pythonScript = pythonScript || path.join(__dirname, 'python_server.py');
    this.buffer = Buffer.alloc(0);
    this.pendingResolve = null;
  }

  /**
   * Spawn the embedded Python IPC server.
   * Returns the process handle for size measurement.
   */
  spawnPython() {
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    
    this.pythonProcess = spawn(pythonCmd, [this.pythonScript], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUNBUFFERED: '1' }
    });

    // Accumulate stdout data until we have a complete message
    this.pythonProcess.stdout.on('data', (chunk) => {
      this.buffer = Buffer.concat([this.buffer, chunk]);
      this._tryProcessMessage();
    });

    this.pythonProcess.stderr.on('data', (data) => {
      console.error(`[Python stderr]: ${data}`);
    });

    this.pythonProcess.on('error', (err) => {
      console.error('[Python spawn error]:', err.message);
    });

    this.pythonProcess.on('exit', (code) => {
      console.log(`[Python process exited with code ${code}]`);
      if (this.pendingResolve) {
        this.pendingResolve({ status: 'error', message: 'Process exited unexpectedly' });
      }
    });

    return this.pythonProcess;
  }

  /**
   * Try to extract a complete message from the buffer.
   * Protocol: 4-byte LE length prefix + JSON body.
   */
  _tryProcessMessage() {
    while (this.buffer.length >= 4) {
      const msgLen = this.buffer.readUInt32LE(0);
      const totalLen = 4 + msgLen;
      
      if (this.buffer.length < totalLen) {
        break; // Wait for more data
      }

      const messageData = this.buffer.slice(4, totalLen);
      this.buffer = this.buffer.slice(totalLen);

      try {
        const response = JSON.parse(messageData.toString('utf-8'));
        if (this.pendingResolve) {
          const resolve = this.pendingResolve;
          this.pendingResolve = null;
          resolve(response);
        }
      } catch (e) {
        console.error('[Parse error]:', e.message);
        if (this.pendingResolve) {
          const resolve = this.pendingResolve;
          this.pendingResolve = null;
          resolve({ status: 'error', message: `Parse error: ${e.message}` });
        }
      }
    }
  }

  /**
   * Send a command to the Python server and wait for response.
   */
  async send(cmd, payload = {}) {
    return new Promise((resolve, reject) => {
      if (!this.pythonProcess || !this.pythonProcess.stdin.writable) {
        return reject(new Error('Python process not running'));
      }

      this.pendingResolve = resolve;
      const message = JSON.stringify({ cmd, payload });
      const header = Buffer.alloc(4);
      header.writeUInt32LE(Buffer.byteLength(message));
      this.pythonProcess.stdin.write(Buffer.concat([header, Buffer.from(message, 'utf-8')]));
    });
  }

  /**
   * Benchmark: measure round-trip latency for a given payload.
   */
  async benchmarkLatency(payload, iterations = 100) {
    const times = [];
    for (let i = 0; i < iterations; i++) {
      const start = process.hrtime.bigint();
      await this.send('echo', payload);
      const end = process.hrtime.bigint();
      times.push(Number(end - start) / 1e6); // Convert to ms
    }
    
    const avg = times.reduce((a, b) => a + b, 0) / times.length;
    const min = Math.min(...times);
    const max = Math.max(...times);
    
    return { avg, min, max, iterations, unit: 'ms' };
  }

  /**
   * Benchmark: transfer a large payload and measure throughput.
   */
  async benchmarkThroughput() {
    const start = process.hrtime.bigint();
    const result = await this.send('size_benchmark');
    const end = process.hrtime.bigint();
    const elapsedMs = Number(end - start) / 1e6;
    
    const payloadSizeBytes = result.payload_size_bytes || 0;
    const throughputMbps = (payloadSizeBytes * 8) / (elapsedMs / 1000) / 1e6;
    
    return {
      elapsed_ms: elapsedMs,
      payload_size_bytes: payloadSizeBytes,
      throughput_mbps: throughputMbps
    };
  }

  shutdown() {
    if (this.pythonProcess) {
      this.pythonProcess.stdin.end();
      this.pythonProcess.kill();
      this.pythonProcess = null;
    }
  }
}

// Export for testing
if (typeof module !== 'undefined') {
  module.exports = { RameshIPCBridge };
}

// Standalone test if run directly
if (require.main === module) {
  (async () => {
    console.log('🚀 Ramesh Saini v7.1 - IPC Bridge Test');
    const bridge = new RameshIPCBridge();
    bridge.spawnPython();

    // Wait for Python to start
    await new Promise(r => setTimeout(r, 1000));

    // Test 1: Basic echo
    console.log('\n📡 Test 1: Basic Echo');
    const echoResult = await bridge.send('echo', { hello: 'world', timestamp: Date.now() });
    console.log('  Response:', JSON.stringify(echoResult).substring(0, 100) + '...');

    // Test 2: Latency benchmark (small payload)
    console.log('\n⏱️  Test 2: Latency Benchmark (100 iterations)');
    const latencyResult = await bridge.benchmarkLatency({ ping: true }, 100);
    console.log(`  Avg: ${latencyResult.avg.toFixed(2)}ms | Min: ${latencyResult.min.toFixed(2)}ms | Max: ${latencyResult.max.toFixed(2)}ms`);

    // Test 3: Large payload throughput
    console.log('\n📦 Test 3: 10MB Payload Throughput');
    const throughputResult = await bridge.benchmarkThroughput();
    console.log(`  Elapsed: ${throughputResult.elapsed_ms.toFixed(2)}ms`);
    console.log(`  Payload: ${(throughputResult.payload_size_bytes / 1024 / 1024).toFixed(2)}MB`);
    console.log(`  Throughput: ${throughputResult.throughput_mbps.toFixed(2)} Mbps`);

    // Verify constraints
    const latencyOk = latencyResult.avg < 50;
    console.log(`\n✅ IPC Latency < 50ms: ${latencyOk ? 'PASS' : 'FAIL'} (${latencyResult.avg.toFixed(2)}ms)`);
    
    bridge.shutdown();
    console.log('\n✨ PoC 1 complete.');
  })().catch(err => {
    console.error('Fatal:', err);
    process.exit(1);
  });
}
