/**
 * Sui Transaction Service
 * 
 * Express API for executing Sui blockchain transactions.
 * Handles oracle updates and position liquidations for Tumo protocol.
 * 
 * Running on Bun runtime for better performance.
 * 
 * IMPROVEMENTS:
 * - Separated wallets for sponsor vs operations (oracle/liquidation)
 * - Enhanced logging for debugging object version conflicts
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

// ⭐ DUAL WALLET SETUP
const SPONSOR_MNEMONIC = process.env.SPONSOR_MNEMONIC;
const OPERATIONS_MNEMONIC = process.env.OPERATIONS_MNEMONIC || process.env.MNEMONIC; // Fallback to old MNEMONIC

if (!SPONSOR_MNEMONIC) {
  throw new Error('SPONSOR_MNEMONIC environment variable is required');
}

if (!OPERATIONS_MNEMONIC) {
  throw new Error('OPERATIONS_MNEMONIC (or MNEMONIC) environment variable is required');
}

// Tumo Protocol Configuration
const PACKAGE_ID = process.env.PACKAGE_ID || "0x255d4eb897177a6749ae4a3b54b6833afca05587b794adeab6e3c12a453f41a6";
const PRICE_FEED_CAP_ID = process.env.PRICE_FEED_CAP_ID || "0xea6f4607f45da2c9855e776909b8eaeb30fb8337d0dceda37131c0bb8fa23350";
const PRICE_FEED_ID = process.env.PRICE_FEED_ID || "0xc2cb74f22555a0a7b991ec80f68a3d25ecbbe50296fef634c821e88a91884bbd";
const MARKET_BTC_ID = process.env.MARKET_BTC_ID || "0x484657984f8170c8c42038ab693b8a0a0ead6970a31d81628d6c00c483025bc5";
const LIQUIDITY_POOL_ID = process.env.LIQUIDITY_POOL_ID || "0xbba60cc9830e27822d813d08ecc336330265b4e0196fa7c5081440754fac4f78";

// Token Types
const BTC_TYPE = '0x81c52254ccd626b128aab686c70a43fe0c50423ea10ee5b3921e10e198fbcbf9::btc::BTC';
const OCT_TYPE = "0x0000000000000000000000000000000000000000000000000000000000000002::oct::OCT";
const USDH_TYPE = process.env.USDH_TYPE || "0xdd0d096ded419429ca4cbe948aa01cedfc842eb151eb6a73af0398406a8cfb07::usdh::USDH";
const HACKATHON_TYPE = process.env.HACKATHON_TYPE || "0x8b76fc2a2317d45118770cefed7e57171a08c477ed16283616b15f099391f120::hackathon::HACKATHON";

// =============================================================================
// SUI CLIENT SETUP
// =============================================================================

const suiClient = new SuiClient({ 
  url: getFullnodeUrl(NETWORK as any) 
});

// ⭐ TWO SEPARATE SIGNERS
const sponsorSigner = Ed25519Keypair.deriveKeypair(SPONSOR_MNEMONIC, "m/44'/784'/0'/0'/0'");
const operationsSigner = Ed25519Keypair.deriveKeypair(OPERATIONS_MNEMONIC, "m/44'/784'/0'/0'/0'");

console.log('🔐 Sponsor wallet:', sponsorSigner.getPublicKey().toSuiAddress());
console.log('⚙️  Operations wallet:', operationsSigner.getPublicKey().toSuiAddress());

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

type GasCoinRef = { objectId: string; version: string | number; digest: string };

async function getSponsorGasPayment(limit = 8): Promise<GasCoinRef[]> {
  const sponsorAddress = sponsorSigner.getPublicKey().toSuiAddress();

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

// ⭐ ENHANCED OBJECT CONFLICT DETECTION
function looksLikeStaleObjectError(errMsg: string): boolean {
  const m = errMsg.toLowerCase();
  return (
    m.includes('not available for consumption') ||
    m.includes('current version') ||
    m.includes('object version') ||
    m.includes('is not available') ||
    m.includes('error checking transaction input objects') ||
    (m.includes('version') && m.includes('digest'))
  );
}

async function logObjectDetails(objectId: string, label: string) {
  try {
    const obj = await suiClient.getObject({
      id: objectId,
      options: { 
        showType: true, 
        showOwner: true, 
        showContent: true 
      },
    });
    
    console.log(`  📦 ${label}:`);
    console.log(`     ID: ${objectId}`);
    console.log(`     Type: ${obj.data?.type || 'unknown'}`);
    console.log(`     Owner: ${JSON.stringify(obj.data?.owner)}`);
    console.log(`     Version: ${obj.data?.version}`);
  } catch (e) {
    console.log(`  📦 ${label}: ${objectId} (could not fetch details)`);
  }
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
    sponsorWallet: sponsorSigner.getPublicKey().toSuiAddress(),
    operationsWallet: operationsSigner.getPublicKey().toSuiAddress(),
    runtime: 'bun',
  });
});

// ⭐ Update oracle price - USES OPERATIONS WALLET
app.post('/api/update-price', authMiddleware, async (req: Request, res: Response) => {
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
    
    console.log(`📊 Updating price to: ${price} (using operations wallet)`);
    
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
    
    // ⭐ Execute with OPERATIONS SIGNER
    const result = await suiClient.signAndExecuteTransaction({
      transaction: tx,
      signer: operationsSigner,
      options: {
        showEffects: true,
        showEvents: true,
      },
    });
    
    console.log(`✅ Price updated - TX: ${result.digest}`);
    
    res.json({
      success: true,
      digest: result.digest,
      effects: result.effects,
      events: result.events,
      wallet: 'operations',
    });
    
  } catch (error: any) {
    console.error('❌ Error updating price:', error.message);
    
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to update price',
      details: error.toString(),
    });
  }
});

// ⭐ Liquidate position - USES OPERATIONS WALLET
app.post('/api/liquidate', authMiddleware, async (req: Request, res: Response) => {
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
    
    console.log(`⚡ Liquidating position for user: ${userAddress} (using operations wallet)`);
    
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
      typeArguments: [HACKATHON_TYPE, BTC_TYPE],
    });
    
    // Transfer liquidation reward to liquidator (operations wallet)
    tx.transferObjects([coin], operationsSigner.getPublicKey().toSuiAddress());
    
    // ⭐ Execute with OPERATIONS SIGNER
    const result = await suiClient.signAndExecuteTransaction({
      transaction: tx,
      signer: operationsSigner,
      options: {
        showEffects: true,
        showEvents: true,
      },
    });
    
    console.log(`✅ Position liquidated - TX: ${result.digest}`);
    
    res.json({
      success: true,
      digest: result.digest,
      effects: result.effects,
      events: result.events,
      wallet: 'operations',
    });
    
  } catch (error: any) {
    console.error('❌ Error liquidating position:', error.message);
    
    res.status(500).json({
      success: false,
      error: error.message || 'Failed to liquidate position',
      details: error.toString(),
    });
  }
});

// =============================================================================
// ⭐ Sponsored signing + submission - USES SPONSOR WALLET
// =============================================================================
app.post('/api/sponsored/execute', authMiddleware, async (req: Request, res: Response) => {
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

    const sponsorAddress = sponsorSigner.getPublicKey().toSuiAddress();
    console.log(`🧾 Sponsored execute requested. sponsor=${sponsorAddress}`);

    // Decode tx bytes exactly as user signed
    const txBytes = fromB64(transactionBytesB64);

    // ⭐ ENHANCED LOGGING - Parse transaction to identify objects
    try {
      const tx = Transaction.from(txBytes);
      const txData = tx.getData();
      
      console.log('📋 Transaction Analysis:');
      console.log(`  Sender: ${txData.sender || 'not set'}`);
      console.log(`  Gas Owner: ${txData.gasData?.owner || 'not set'}`);
      
      // Log gas payment objects
      if (txData.gasData?.payment && Array.isArray(txData.gasData.payment)) {
        console.log('  Gas Payment Objects:');
        for (const gasObj of txData.gasData.payment) {
          await logObjectDetails(gasObj.objectId, `Gas Coin`);
        }
      }
      
      // Log input objects
      if (txData.inputs && Array.isArray(txData.inputs)) {
        console.log('  Input Objects:');
        for (let i = 0; i < txData.inputs.length; i++) {
          const input = txData.inputs[i];
          
          if (input.type === 'object') {
            const objValue = (input as any).value;
            if (objValue?.Object?.ImmOrOwned) {
              await logObjectDetails(
                objValue.Object.ImmOrOwned.objectId,
                `Input[${i}] (Owned, v${objValue.Object.ImmOrOwned.version})`
              );
            } else if (objValue?.Object?.Shared) {
              console.log(`  📦 Input[${i}]: ${objValue.Object.Shared.objectId} (Shared)`);
            }
          }
        }
      }
      
    } catch (parseError) {
      console.log('⚠️  Could not parse transaction for logging:', parseError);
    }

    // ⭐ DRY-RUN to detect stale objects BEFORE signing
    console.log('🔍 Running dry-run validation...');
    try {
      const dry = await suiClient.dryRunTransactionBlock({
        transactionBlock: txBytes,
      });
      
      const status = (dry as any)?.effects?.status;
      if (status?.status === 'failure') {
        const errMsg = String(status?.error ?? 'Dry run failure');
        console.error('🔴 Dry-run failed:', errMsg);
        
        // ⭐ DETECT AND LOG STALE OBJECT
        if (looksLikeStaleObjectError(errMsg)) {
          console.error('⚠️  STALE OBJECT DETECTED!');
          
          // Extract object ID and version from error
          const objectIdMatch = errMsg.match(/Object ID (0x[a-fA-F0-9]+)/);
          const expectedVersionMatch = errMsg.match(/Version (0x[a-fA-F0-9]+)/);
          const currentVersionMatch = errMsg.match(/current version: (0x[a-fA-F0-9]+)/);
          
          if (objectIdMatch) {
            console.error(`  Problem Object ID: ${objectIdMatch[1]}`);
            if (expectedVersionMatch) {
              console.error(`  Expected Version: ${expectedVersionMatch[1]}`);
            }
            if (currentVersionMatch) {
              console.error(`  Current Version: ${currentVersionMatch[1]}`);
            }
            
            // Fetch and log object type
            await logObjectDetails(objectIdMatch[1], 'STALE OBJECT');
          }
          
          return res.status(409).json({
            success: false,
            code: 'NEED_RESIGN_STALE_OBJECT',
            error: 'Transaction bytes are stale (object version changed). User must rebuild & re-sign.',
            details: errMsg,
            problemObject: objectIdMatch ? objectIdMatch[1] : undefined,
          });
        }
        
        return res.status(400).json({
          success: false,
          code: 'DRY_RUN_FAILED',
          error: 'Dry run failed',
          details: errMsg,
        });
      }
      
      console.log('✅ Dry-run passed');
      
    } catch (dryErr: any) {
      const errMsg = String(dryErr?.message ?? dryErr);
      console.error('🔴 Dry-run RPC error:', errMsg);
      
      if (looksLikeStaleObjectError(errMsg)) {
        console.error('⚠️  STALE OBJECT detected in dry-run error');
        return res.status(409).json({
          success: false,
          code: 'NEED_RESIGN_STALE_OBJECT',
          error: 'Transaction bytes are stale (object version changed). User must rebuild & re-sign.',
          details: errMsg,
        });
      }
      
      return res.status(400).json({
        success: false,
        code: 'DRY_RUN_RPC_ERROR',
        error: 'Dry run RPC error',
        details: errMsg,
      });
    }

    // ⭐ Sponsor signs with SPONSOR WALLET
    console.log('✍️  Sponsor signing transaction...');
    const sponsorSignature = await sponsorSigner.signTransaction(txBytes);

    // Execute with BOTH signatures: [user, sponsor]
    console.log('🚀 Executing transaction...');
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
      wallet: 'sponsor',
      effects: result.effects,
      events: result.events,
      objectChanges: result.objectChanges,
      confirmedLocalExecution: (result as any).confirmedLocalExecution ?? false,
    });
    
  } catch (error: any) {
    const msg = String(error?.message ?? error);
    console.error('❌ Error executing sponsored tx:', msg);

    // ⭐ FINAL CHECK for stale object error
    if (looksLikeStaleObjectError(msg)) {
      console.error('⚠️  STALE OBJECT detected in execute error');
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

// Get signer info (authenticated)
app.get('/api/signer', authMiddleware, (req: Request, res: Response) => {
  res.json({
    sponsor: sponsorSigner.getPublicKey().toSuiAddress(),
    operations: operationsSigner.getPublicKey().toSuiAddress(),
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
  console.log('');
  console.log('💼 Wallets:');
  console.log(`  🔐 Sponsor:    ${sponsorSigner.getPublicKey().toSuiAddress()}`);
  console.log(`  ⚙️  Operations: ${operationsSigner.getPublicKey().toSuiAddress()}`);
  console.log('');
  console.log(`📦 Package: ${PACKAGE_ID}`);
  console.log(`⚡ Runtime: Bun ${Bun.version}`);
  console.log('');
  console.log('Available endpoints:');
  console.log('  GET  /health                 - Health check');
  console.log('  POST /api/update-price       - Update oracle price (operations wallet)');
  console.log('  POST /api/liquidate          - Liquidate position (operations wallet)');
  console.log('  POST /api/sponsored/execute  - Sponsor-sign + submit (sponsor wallet)');
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
