/**
 * WebSocket Client Examples for Derivatives Protocol
 * 
 * These examples show how to connect to various WebSocket endpoints
 * from your frontend application.
 */

// ============================================================================
// 1. PRICE UPDATES - Real-time price stream for a market
// ============================================================================

function subscribeToPrices(marketId) {
    const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/prices/${marketId}`);
    
    ws.onopen = () => {
        console.log(`Connected to price stream for ${marketId}`);
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'connected') {
            console.log('Connected:', data.message);
        } 
        else if (data.type === 'price_update') {
            // Update UI with new price
            console.log(`${data.symbol}: $${data.price}`);
            updatePriceUI(data.market_id, data.price, data.confidence);
        }
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    ws.onclose = () => {
        console.log('Price stream disconnected');
        // Attempt to reconnect after 5 seconds
        setTimeout(() => subscribeToPrices(marketId), 5000);
    };
    
    return ws;
}

// Usage
const btcPriceWs = subscribeToPrices('btc-usdc-perp');


// ============================================================================
// 2. POSITION UPDATES - Real-time PnL and health for user's positions
// ============================================================================

function subscribeToPositions(userAddress) {
    const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/positions/${userAddress}`);
    
    ws.onopen = () => {
        console.log(`Connected to position updates for ${userAddress}`);
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'positions_update') {
            console.log(`Total Unrealized PnL: $${data.total_unrealized_pnl}`);
            
            // Update each position
            data.positions.forEach(position => {
                console.log(`Position ${position.position_id}:`);
                console.log(`  - Unrealized PnL: $${position.unrealized_pnl}`);
                console.log(`  - Health Factor: ${position.health_factor}`);
                
                if (position.is_at_risk) {
                    showWarning(`Position at risk! Health: ${position.health_factor}`);
                }
                
                updatePositionUI(position);
            });
        }
        else if (data.type === 'liquidation_warning') {
            // CRITICAL: Show urgent warning to user
            showUrgentAlert(
                `⚠️ LIQUIDATION WARNING!\n` +
                `Position ${data.data.position_id} is at risk!\n` +
                `Health Factor: ${data.data.health_factor}\n` +
                `Liquidation Price: $${data.data.liquidation_price}`
            );
        }
        else if (data.type === 'position_opened') {
            showNotification(`New position opened: ${data.data.side} ${data.data.size}`);
            refreshPositionList();
        }
        else if (data.type === 'position_closed') {
            showNotification(`Position closed. PnL: $${data.data.realized_pnl}`);
            refreshPositionList();
        }
        else if (data.type === 'position_liquidated') {
            showAlert(`❌ Position liquidated at $${data.data.liquidation_price}`);
            refreshPositionList();
        }
    };
    
    ws.onerror = (error) => {
        console.error('Position WebSocket error:', error);
    };
    
    ws.onclose = () => {
        console.log('Position updates disconnected');
        setTimeout(() => subscribeToPositions(userAddress), 5000);
    };
    
    return ws;
}

// Usage
const userWalletAddress = '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb';
const positionsWs = subscribeToPositions(userWalletAddress);


// ============================================================================
// 3. LIQUIDATION ALERTS - Monitor positions at risk
// ============================================================================

function subscribeToLiquidations() {
    const ws = new WebSocket('ws://localhost:8000/api/v1/ws/liquidations');
    
    ws.onopen = () => {
        console.log('Connected to liquidation alerts');
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'liquidation_alert') {
            console.log(`${data.count} positions at risk of liquidation`);
            
            // Display liquidation opportunities
            data.candidates.forEach(candidate => {
                console.log(`Liquidation Opportunity:`);
                console.log(`  - Position: ${candidate.position_id}`);
                console.log(`  - Health: ${candidate.health_factor}`);
                console.log(`  - Reward: $${candidate.potential_reward}`);
            });
            
            updateLiquidationDashboard(data.candidates);
        }
    };
    
    ws.onerror = (error) => {
        console.error('Liquidation WebSocket error:', error);
    };
    
    ws.onclose = () => {
        console.log('Liquidation alerts disconnected');
        setTimeout(subscribeToLiquidations, 5000);
    };
    
    return ws;
}

// Usage (for liquidation bots or dashboards)
const liquidationsWs = subscribeToLiquidations();


// ============================================================================
// 4. MARKET STATS - Real-time market statistics
// ============================================================================

function subscribeToMarketStats(marketId) {
    const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/market-stats/${marketId}`);
    
    ws.onopen = () => {
        console.log(`Connected to market stats for ${marketId}`);
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'market_stats') {
            console.log(`Market: ${data.symbol}`);
            console.log(`  - Price: $${data.current_price}`);
            console.log(`  - Total OI: $${data.total_oi}`);
            console.log(`  - Funding Rate: ${data.funding_rate}`);
            
            updateMarketStatsUI(data);
        }
        else if (data.type === 'funding_rate_update') {
            console.log(`Funding rate updated: ${data.data.funding_rate}`);
            showNotification(`Funding rate changed to ${data.data.funding_rate}`);
        }
    };
    
    ws.onerror = (error) => {
        console.error('Market stats WebSocket error:', error);
    };
    
    ws.onclose = () => {
        console.log('Market stats disconnected');
        setTimeout(() => subscribeToMarketStats(marketId), 5000);
    };
    
    return ws;
}

// Usage
const marketStatsWs = subscribeToMarketStats('btc-usdc-perp');


// ============================================================================
// HELPER FUNCTIONS (implement these in your UI)
// ============================================================================

function updatePriceUI(marketId, price, confidence) {
    // Update your price display
    const priceElement = document.getElementById(`price-${marketId}`);
    if (priceElement) {
        priceElement.textContent = `$${parseFloat(price).toLocaleString()}`;
    }
}

function updatePositionUI(position) {
    // Update position card in UI
    const positionElement = document.getElementById(`position-${position.position_id}`);
    if (positionElement) {
        // Update PnL, health factor, etc.
        positionElement.querySelector('.pnl').textContent = position.unrealized_pnl;
        positionElement.querySelector('.health').textContent = position.health_factor;
        
        // Add warning class if at risk
        if (position.is_at_risk) {
            positionElement.classList.add('warning');
        }
    }
}

function showWarning(message) {
    // Show warning toast/notification
    console.warn(message);
    // Your toast notification code here
}

function showUrgentAlert(message) {
    // Show urgent modal or alert
    alert(message); // Replace with better UI
}

function showNotification(message) {
    // Show info notification
    console.log(message);
    // Your notification code here
}

function showAlert(message) {
    // Show alert notification
    console.log(message);
    // Your alert code here
}

function refreshPositionList() {
    // Refresh your position list from API
    console.log('Refreshing position list...');
}

function updateLiquidationDashboard(candidates) {
    // Update liquidation opportunities dashboard
    console.log('Updating liquidation dashboard...');
}

function updateMarketStatsUI(stats) {
    // Update market statistics display
    console.log('Updating market stats UI...');
}


// ============================================================================
// COMPLETE EXAMPLE - Trading Dashboard
// ============================================================================

class TradingDashboard {
    constructor(userAddress) {
        this.userAddress = userAddress;
        this.websockets = {};
    }
    
    connect() {
        // Connect to position updates
        this.websockets.positions = subscribeToPositions(this.userAddress);
        
        // Connect to price updates for all markets
        const markets = ['btc-usdc-perp', 'eth-usdc-perp', 'sol-usdc-perp'];
        markets.forEach(marketId => {
            this.websockets[`price-${marketId}`] = subscribeToPrices(marketId);
        });
        
        // Connect to liquidation alerts
        this.websockets.liquidations = subscribeToLiquidations();
    }
    
    disconnect() {
        // Close all websocket connections
        Object.values(this.websockets).forEach(ws => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.close();
            }
        });
        this.websockets = {};
    }
}

// Usage
const dashboard = new TradingDashboard('0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb');
dashboard.connect();

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    dashboard.disconnect();
});
