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
const PACKAGE_ID = process.env.PACKAGE_ID || "0x31b6ea6f6c2e1727d590fba2b6ccd93dd0785f238fd91cb16030d468a466bc6e";
const PRICE_FEED_CAP_ID = process.env.PRICE_FEED_CAP_ID || "0x254fe1a8ab857148afafb0ed905bb74f18b14aaeca0766c9d55cdccdb7f11a13";
const PRICE_FEED_ID = process.env.PRICE_FEED_ID || "0x160af47fc46e4541383ac21b08109bbd4b84ed370c13a1269863d6e6bfd7775e";
const MARKET_BTC_ID = process.env.MARKET_BTC_ID || "0x4fd1a0468f23e87650c300f94e83aedc1d74d737e83a1f7f9e012dc6bdc1fd51";
const LIQUIDITY_POOL_ID = process.env.LIQUIDITY_POOL_ID || "0xfd91ba1536e2d08c73fc4706249964d7490c9f12fe4987f87f5362d9bf36e3f2";

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
    
    res.json({
      success: true,
      digest: result.digest,
      effects: result.effects,
      events: result.events,
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

// Liquidate position
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
    
    res.json({
      success: true,
      digest: result.digest,
      effects: result.effects,
      events: result.events,
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
// Sponsored signing + submission endpoint
// =============================================================================
app.post('/api/sponsored/execute', authMiddleware, async (req: Request, res: Response) => {
  try {
    const { kindBytesB64, userSignatureB64, sender, gasBudget } = req.body ?? {};

    if (!kindBytesB64 || typeof kindBytesB64 !== 'string') {
      return res.status(400).json({
        success: false,
        error: 'kindBytesB64 is required (base64 TransactionKind)',
      });
    }

    if (!userSignatureB64 || typeof userSignatureB64 !== 'string') {
      return res.status(400).json({
        success: false,
        error: 'userSignatureB64 is required (base64 signature)',
      });
    }

    if (!sender || typeof sender !== 'string' || !/^0x[a-fA-F0-9]{64}$/.test(sender)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid sender address format',
      });
    }

    if (gasBudget !== undefined && typeof gasBudget !== 'number') {
      return res.status(400).json({
        success: false,
        error: 'gasBudget must be a number if provided',
      });
    }

    const sponsorAddress = signer.getPublicKey().toSuiAddress();
    console.log(`🧾 Sponsored execute requested. sender=${sender} sponsor=${sponsorAddress}`);

    // Reconstruct tx from kind bytes
    const tx = Transaction.fromKind(kindBytesB64);

    // Sponsor setup
    tx.setSender(sender);
    tx.setGasOwner(sponsorAddress);

    const gasPayment = await getSponsorGasPayment();
    if (!gasPayment.length) {
      return res.status(400).json({
        success: false,
        error: 'Sponsor has no gas coins (OCT) to pay gas',
      });
    }
    tx.setGasPayment(gasPayment);

    // Optional: set deterministic gas budget
    if (typeof gasBudget === 'number') {
      tx.setGasBudget(BigInt(gasBudget));
    }

    // Build final tx bytes
    const txBytes = await tx.build({ client: suiClient });

    // Sponsor signs the tx bytes
    const sponsorSignature = await signer.signTransaction(txBytes);

    // Execute with BOTH signatures: [user, sponsor]
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
    console.error('❌ Error executing sponsored tx:', error?.message ?? error);

    return res.status(500).json({
      success: false,
      error: error?.message || 'Failed to execute sponsored transaction',
      details: String(error),
    });
  }
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
  console.log('  POST /api/sponsored/execute  - Sponsor-sign + submit (called by Python backend)');
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
