/**
 * Sui Transaction Service
 * 
 * Express API for executing Sui blockchain transactions.
 * Handles oracle updates and position liquidations for Tumo protocol.
 * 
 * Running on Bun runtime for better performance.
 */

import { SuiClient, getFullnodeUrl } from '@onelabs/sui/client';
import { Ed25519Keypair } from '@onelabs/sui/keypairs/ed25519';
import { Transaction } from '@onelabs/sui/transactions';
import { fromB64 } from '@onelabs/sui/utils';
import express, { NextFunction, Request, Response } from 'express';
import swaggerUi from "swagger-ui-express";
import { openapiSpec } from "./openapi";

// =============================================================================
// CONFIGURATION
// =============================================================================
// Note: Bun automatically loads .env file - no need for dotenv package!

const PORT = process.env.PORT || 3001;
const NETWORK = process.env.NETWORK || 'testnet';
const API_KEY = process.env.API_KEY || 'change-me-in-production';
const MNEMONIC = process.env.MNEMONIC;

if (!MNEMONIC) {
  throw new Error('MNEMONIC environment variable is required');
}

// Tumo Protocol Configuration
const PACKAGE_ID = process.env.PACKAGE_ID || "0x3d027f54a56da8f7ff37202acd710d7e09c5b4754390495fc194b4aa8545c8da";
const PRICE_FEED_CAP_ID = process.env.PRICE_FEED_CAP_ID || "0x5043fc95b7f09f12f2bf13f0ec26e7c788fed90c35cbd56c1878735f0c52653a";
const PRICE_FEED_ID = process.env.PRICE_FEED_ID || "0xa038c0823cd32d5f2745b119e0bc9b6261582bebc679a2c15a134de24045ca42";
const MARKET_BTC_ID = process.env.MARKET_BTC_ID || "0x2ba0f2dd3b1fe3544c6617dd14ea12518ae2596860763b144e78866dc9b556fc";
const LIQUIDITY_POOL_ID = process.env.LIQUIDITY_POOL_ID || "0x1855575f8b2833526c9a8c90f36a37d960f4ea79c9e522adad93488a566a9dfa";

// Token Types
const BTC_TYPE = '0x81c52254ccd626b128aab686c70a43fe0c50423ea10ee5b3921e10e198fbcbf9::btc::BTC';
const OCT_TYPE = "0x0000000000000000000000000000000000000000000000000000000000000002::oct::OCT";
const USDH_TYPE = process.env.USDH_TYPE || "0xdd0d096ded419429ca4cbe948aa01cedfc842eb151eb6a73af0398406a8cfb07::usdh::USDH";

// =============================================================================
// SUI CLIENT SETUP
// =============================================================================

const suiClient = new SuiClient({ 
  url: getFullnodeUrl(NETWORK as any) 
});

const signer = Ed25519Keypair.deriveKeypair(MNEMONIC, "m/44'/784'/0'/0'/0'");

console.log('🔐 Signer address:', signer.getPublicKey().toSuiAddress());

type GasCoinRef = { objectId: string; version: string | number; digest: string };

async function getSponsorGasPayment(limit = 8): Promise<GasCoinRef[]> {
  const sponsorAddress = signer.getPublicKey().toSuiAddress();

  const coins = await suiClient.getCoins({
    owner: sponsorAddress,
    coinType: OCT_TYPE,
    limit,
  });

  return coins.data.map((c) => ({
    objectId: c.coinObjectId,
    version: c.version,
    digest: c.digest,
  }));
}

// =============================================================================
// SIMPLE GLOBAL MUTEX (serialize tx submission inside THIS service)
// =============================================================================

class Mutex {
  private locked = false;
  private waiters: Array<() => void> = [];

  async acquire(): Promise<() => void> {
    return new Promise((resolve) => {
      const tryAcquire = () => {
        if (!this.locked) {
          this.locked = true;
          resolve(() => this.release());
          return;
        }
        this.waiters.push(tryAcquire);
      };
      tryAcquire();
    });
  }

  private release() {
    const next = this.waiters.shift();
    if (next) {
      next();
    } else {
      this.locked = false;
    }
  }
}

const txMutex = new Mutex();

async function withTxLock<T>(fn: () => Promise<T>): Promise<T> {
  const release = await txMutex.acquire();
  try {
    return await fn();
  } finally {
    release();
  }
}

// Try to detect stale-object error messages and return a clear code upstream
function looksLikeStaleObjectError(errMsg: string): boolean {
  const m = errMsg.toLowerCase();
  return (
    m.includes('not available for consumption') ||
    m.includes('current version') ||
    m.includes('object version') ||
    m.includes('version') && m.includes('digest') && m.includes('is not available')
  );
}

// =============================================================================
// EXPRESS APP
// =============================================================================

const app = express();

app.get("/openapi.json", (req, res) => res.json(openapiSpec));
app.use("/docs", swaggerUi.serve, swaggerUi.setup(openapiSpec, {
  swaggerOptions: { persistAuthorization: true },
}));

// Middleware
app.use(express.json());

// Request logging
app.use((req: Request, res: Response, next: NextFunction) => {
  console.log(`${new Date().toISOString()} ${req.method} ${req.path}`);
  next();
});

// API Key authentication
const authMiddleware = (req: Request, res: Response, next: NextFunction) => {
  const apiKey = req.headers['x-api-key'];
  
  if (apiKey !== API_KEY) {
    return res.status(401).json({
      success: false,
      error: 'Unauthorized - Invalid API key',
    });
  }
  
  next();
};

// =============================================================================
// ROUTES
// =============================================================================

// Health check (no auth required)
app.get('/health', (req: Request, res: Response) => {
  res.json({
    status: 'healthy',
    service: 'sui-tx-service',
    network: NETWORK,
    timestamp: new Date().toISOString(),
    signer: signer.getPublicKey().toSuiAddress(),
    runtime: 'bun',
  });
});

// Update oracle price
app.post('/api/update-price', authMiddleware, async (req: Request, res: Response) => {
  return withTxLock(async () => {
    try {
      const { price } = req.body;
      
      // Validate input
      if (!price || typeof price !== 'number') {
        return res.status(400).json({
          success: false,
          error: 'Invalid price - must be a number',
        });
      }
      
      if (price <= 0) {
        return res.status(400).json({
          success: false,
          error: 'Price must be greater than 0',
        });
      }
      
      console.log(`📊 Updating price to: ${price}`);
      
      // Build transaction
      const tx = new Transaction();
      
      tx.moveCall({
        target: `${PACKAGE_ID}::oracle::update_price`,
        arguments: [
          tx.object(PRICE_FEED_CAP_ID),
          tx.object(PRICE_FEED_ID),
          tx.pure.u64(BigInt(price)),
          tx.object("0x6"), // Clock object
        ],
        typeArguments: [BTC_TYPE],
      });
      
      // Execute transaction
      const result = await suiClient.signAndExecuteTransaction({
        transaction: tx,
        signer: signer,
        options: {
          showEffects: true,
          showEvents: true,
        },
      });
      
      console.log(`✅ Price updated - TX: ${result.digest}`);
      
      return res.json({
        success: true,
        digest: result.digest,
        effects: result.effects,
        events: result.events,
      });
      
    } catch (error: any) {
      console.error('❌ Error updating price:', error.message);
      
      return res.status(500).json({
        success: false,
        error: error.message || 'Failed to update price',
        details: error.toString(),
      });
    }
  });
});

// Liquidate position
app.post('/api/liquidate', authMiddleware, async (req: Request, res: Response) => {
  return withTxLock(async () => {
    try {
      const { userAddress } = req.body;
      
      // Validate input
      if (!userAddress || typeof userAddress !== 'string') {
        return res.status(400).json({
          success: false,
          error: 'Invalid userAddress - must be a string',
        });
      }
      
      // Validate Sui address format (0x followed by 64 hex chars)
      if (!/^0x[a-fA-F0-9]{64}$/.test(userAddress)) {
        return res.status(400).json({
          success: false,
          error: 'Invalid Sui address format',
        });
      }
      
      console.log(`⚡ Liquidating position for user: ${userAddress}`);
      
      // Build transaction
      const tx = new Transaction();
      
      const coin = tx.moveCall({
        target: `${PACKAGE_ID}::tumo_markets_core::liquidate`,
        arguments: [
          tx.object(MARKET_BTC_ID),
          tx.object(LIQUIDITY_POOL_ID),
          tx.object(PRICE_FEED_ID),
          tx.object("0x6"), // Clock object
          tx.pure.address(userAddress),
        ],
        typeArguments: [USDH_TYPE, BTC_TYPE],
      });
      
      // Transfer liquidation reward to liquidator (signer)
      tx.transferObjects([coin], signer.getPublicKey().toSuiAddress());
      
      // Execute transaction
      const result = await suiClient.signAndExecuteTransaction({
        transaction: tx,
        signer: signer,
        options: {
          showEffects: true,
          showEvents: true,
        },
      });
      
      console.log(`✅ Position liquidated - TX: ${result.digest}`);
      
      return res.json({
        success: true,
        digest: result.digest,
        effects: result.effects,
        events: result.events,
      });
      
    } catch (error: any) {
      console.error('❌ Error liquidating position:', error.message);
      
      return res.status(500).json({
        success: false,
        error: error.message || 'Failed to liquidate position',
        details: error.toString(),
      });
    }
  });
});

// =============================================================================
// Sponsored signing + submission endpoint (NEW FLOW: txBytes already built by FE)
// =============================================================================
app.post('/api/sponsored/execute', authMiddleware, async (req: Request, res: Response) => {
  return withTxLock(async () => {
    try {
      const { transactionBytesB64, userSignatureB64 } = req.body ?? {};

      if (!transactionBytesB64 || typeof transactionBytesB64 !== 'string') {
        return res.status(400).json({
          success: false,
          error: 'transactionBytesB64 is required (base64 full TransactionBlock bytes)',
        });
      }

      if (!userSignatureB64 || typeof userSignatureB64 !== 'string') {
        return res.status(400).json({
          success: false,
          error: 'userSignatureB64 is required (base64 signature)',
        });
      }

      const sponsorAddress = signer.getPublicKey().toSuiAddress();
      console.log(`🧾 Sponsored execute requested (NEW FLOW). sponsor=${sponsorAddress}`);

      // Decode tx bytes exactly as user signed
      const txBytes = fromB64(transactionBytesB64);

      // 1) Dry-run FIRST to detect stale versions early
      // If this fails with "not available for consumption / current version", user must sign again.
      try {
        const dry = await suiClient.dryRunTransactionBlock({
          transactionBlock: txBytes,
        });

        // Some RPCs return failure in effects/status for dry-run
        const status = (dry as any)?.effects?.status;
        if (status?.status === 'failure') {
          const errMsg = String(status?.error ?? 'Dry run failure');
          if (looksLikeStaleObjectError(errMsg)) {
            return res.status(409).json({
              success: false,
              code: 'NEED_RESIGN_STALE_OBJECT',
              error: 'Transaction bytes are stale (object version changed). User must rebuild & re-sign.',
              details: errMsg,
            });
          }
          return res.status(400).json({
            success: false,
            code: 'DRY_RUN_FAILED',
            error: 'Dry run failed',
            details: errMsg,
          });
        }
      } catch (e: any) {
        const errMsg = String(e?.message ?? e);
        if (looksLikeStaleObjectError(errMsg)) {
          return res.status(409).json({
            success: false,
            code: 'NEED_RESIGN_STALE_OBJECT',
            error: 'Transaction bytes are stale (object version changed). User must rebuild & re-sign.',
            details: errMsg,
          });
        }
        // If dry-run RPC itself errors, we can still try execute; but it’s safer to fail fast.
        return res.status(400).json({
          success: false,
          code: 'DRY_RUN_RPC_ERROR',
          error: 'Dry run RPC error',
          details: errMsg,
        });
      }

      // 2) Sponsor signs the SAME tx bytes that user signed
      const sponsorSignature = await signer.signTransaction(txBytes);

      // 3) Execute with BOTH signatures: [user, sponsor]
      const result = await suiClient.executeTransactionBlock({
        transactionBlock: txBytes,
        signature: [userSignatureB64, sponsorSignature.signature],
        options: {
          showEffects: true,
          showEvents: true,
          showObjectChanges: true,
        },
      });

      console.log(`✅ Sponsored tx executed: ${result.digest}`);

      return res.json({
        success: true,
        digest: result.digest,
        sponsorAddress,
        effects: result.effects,
        events: result.events,
        objectChanges: result.objectChanges,
        confirmedLocalExecution: (result as any).confirmedLocalExecution ?? false,
      });
    } catch (error: any) {
      const msg = String(error?.message ?? error);
      console.error('❌ Error executing sponsored tx:', msg);

      // If it still fails due to stale version (race from outside this service),
      // return an explicit code so upstream can ask user to re-sign.
      if (looksLikeStaleObjectError(msg)) {
        return res.status(409).json({
          success: false,
          code: 'NEED_RESIGN_STALE_OBJECT',
          error: 'Transaction bytes are stale (object version changed). User must rebuild & re-sign.',
          details: msg,
        });
      }

      return res.status(500).json({
        success: false,
        error: msg || 'Failed to execute sponsored transaction',
        details: String(error),
      });
    }
  });
});

// Get signer info (authenticated)
app.get('/api/signer', authMiddleware, (req: Request, res: Response) => {
  res.json({
    address: signer.getPublicKey().toSuiAddress(),
    network: NETWORK,
  });
});

// 404 handler
app.use((req: Request, res: Response) => {
  res.status(404).json({
    success: false,
    error: 'Not found',
  });
});

// Error handler
app.use((error: Error, req: Request, res: Response, next: NextFunction) => {
  console.error('Server error:', error);
  
  res.status(500).json({
    success: false,
    error: 'Internal server error',
    details: error.message,
  });
});

// =============================================================================
// START SERVER
// =============================================================================

app.listen(PORT, () => {
  console.log('🚀 Sui Transaction Service (Bun Runtime)');
  console.log(`📡 Listening on port ${PORT}`);
  console.log(`🌍 Network: ${NETWORK}`);
  console.log(`🔐 Signer: ${signer.getPublicKey().toSuiAddress()}`);
  console.log(`📦 Package: ${PACKAGE_ID}`);
  console.log(`⚡ Runtime: Bun ${Bun.version}`);
  console.log('');
  console.log('Available endpoints:');
  console.log('  GET  /health                 - Health check');
  console.log('  POST /api/update-price       - Update oracle price');
  console.log('  POST /api/liquidate          - Liquidate position');
  console.log('  POST /api/sponsored/execute  - Sponsor-sign + submit (NEW FLOW: txBytes)');
  console.log('  GET  /api/signer             - Get signer info');
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('Received SIGTERM, shutting down gracefully...');
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log('Received SIGINT, shutting down gracefully...');
  process.exit(0);
});
