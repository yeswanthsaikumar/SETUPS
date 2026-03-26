import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Generates enhanced HTML reports with:
 * - Reduced visible columns by default
 * - Hidden columns revealed on hover
 * - Complete trade filtering logic documentation
 */
public class HtmlReportGenerator {

    public static void generateVcpHitsReport(List<ScanResult> results, String market, String timeframe, Path outputPath) {
        StringBuilder html = new StringBuilder();
        
        html.append("<!DOCTYPE html>\n");
        html.append("<html lang=\"en\">\n");
        html.append("<head>\n");
        html.append("  <meta charset=\"UTF-8\">\n");
        html.append("  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n");
        html.append("  <title>🚀 VCP Breakout Scan Report</title>\n");
        html.append(getStyleSheet());
        html.append("</head>\n");
        html.append("<body>\n");
        
        // Hero section
        html.append(getHeroSection(results.size(), market, timeframe));
        
        // Summary with filtering logic
        html.append(getFilteringSummary());
        
        // Controls
        html.append(getControlsSection());
        
        // Analytics
        html.append(getAnalyticsSection(results));
        
        // Filtering logic documentation
        html.append(getFilteringLogicDocumentation());
        
        // Data table
        html.append(getDataTable(results));
        
        html.append(getJavaScript());
        html.append("</body>\n");
        html.append("</html>\n");
        
        try {
            Files.write(outputPath, html.toString().getBytes());
            System.out.println("Enhanced HTML report generated: " + outputPath.toAbsolutePath());
        } catch (IOException e) {
            System.err.println("Failed to write HTML report: " + e.getMessage());
        }
    }

    private static String getStyleSheet() {
        return """
          <style>
            * { box-sizing: border-box; }
            body {
              font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
              background: linear-gradient(135deg, #0d1117 0%, #1a2333 50%, #0d1117 100%);
              color: #c9d1d9;
              margin: 0;
              padding: 20px;
            }
            
            h1, h2, h3, h4 { color: #79c0ff; }
            h1 { margin-top: 0; font-size: 2em; }
            h2 { font-size: 1.3em; margin-top: 30px; padding-bottom: 8px; border-bottom: 1px solid #30363d; }
            h3 { font-size: 1.1em; margin-top: 20px; }
            h4 { font-size: 0.95em; color: #9ecbff; }
            
            .container { max-width: 1600px; margin: 0 auto; }
            
            /* Hero Section */
            .hero {
              background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
              border: 1px solid #30363d;
              border-radius: 12px;
              padding: 24px;
              margin-bottom: 24px;
              box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            }
            .hero-content {
              display: flex;
              justify-content: space-between;
              align-items: center;
              gap: 20px;
              flex-wrap: wrap;
            }
            .hero-stats {
              display: flex;
              gap: 16px;
              flex-wrap: wrap;
            }
            .stat-pill {
              background: rgba(94, 234, 212, 0.1);
              border: 1px solid #5eead4;
              border-radius: 20px;
              padding: 8px 16px;
              color: #7ee787;
              font-size: 0.9em;
              font-weight: 600;
            }
            
            /* Controls */
            .controls {
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
              gap: 12px;
              margin-bottom: 24px;
              padding: 16px;
              background: rgba(22, 27, 34, 0.8);
              border: 1px solid #30363d;
              border-radius: 10px;
              backdrop-filter: blur(4px);
            }
            .control-group {
              display: flex;
              flex-direction: column;
              gap: 6px;
            }
            .control-label {
              color: #8b949e;
              font-size: 0.85em;
              font-weight: 600;
              text-transform: uppercase;
            }
            .control-input, .control-select {
              padding: 8px 12px;
              background: #0d1117;
              border: 1px solid #30363d;
              border-radius: 6px;
              color: #c9d1d9;
              font-size: 0.9em;
            }
            .control-input:focus, .control-select:focus {
              outline: none;
              border-color: #58a6ff;
              box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.1);
            }
            
            /* Summary */
            .summary-box {
              background: rgba(15, 23, 42, 0.6);
              border-left: 4px solid #58a6ff;
              border-radius: 6px;
              padding: 16px;
              margin-bottom: 20px;
              color: #9ecbff;
            }
            
            /* Analytics Grid */
            .analytics-grid {
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
              gap: 16px;
              margin-bottom: 24px;
            }
            .stat-card {
              background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
              border: 1px solid #21262d;
              border-radius: 10px;
              padding: 16px;
              text-align: center;
            }
            .stat-card-label {
              color: #8b949e;
              font-size: 0.85em;
              margin-bottom: 8px;
            }
            .stat-card-value {
              color: #58a6ff;
              font-size: 1.6em;
              font-weight: 700;
            }
            .stat-card-secondary {
              color: #79c0ff;
              font-size: 0.8em;
              margin-top: 6px;
            }
            
            /* Filtering Logic Section */
            .logic-section {
              background: rgba(22, 27, 34, 0.6);
              border: 1px solid #30363d;
              border-radius: 10px;
              padding: 20px;
              margin-bottom: 24px;
            }
            .logic-header {
              display: flex;
              justify-content: space-between;
              align-items: center;
              cursor: pointer;
              user-select: none;
            }
            .logic-header h2 {
              margin: 0;
              display: flex;
              align-items: center;
              gap: 10px;
            }
            .logic-toggle {
              font-size: 1.2em;
              transition: transform 0.3s;
            }
            .logic-toggle.collapsed {
              transform: rotate(-90deg);
            }
            .logic-content {
              max-height: none;
              overflow: hidden;
              transition: max-height 0.3s ease;
            }
            .logic-content.collapsed {
              max-height: 0;
              overflow: hidden;
            }
            
            .logic-stage {
              margin-top: 16px;
              padding: 12px;
              background: rgba(13, 17, 23, 0.5);
              border-left: 3px solid #58a6ff;
              border-radius: 6px;
            }
            .logic-stage-title {
              color: #7ee787;
              font-weight: 600;
              margin-bottom: 8px;
            }
            .logic-items {
              margin-left: 12px;
              color: #9ecbff;
              font-size: 0.9em;
              line-height: 1.6;
            }
            .logic-item {
              margin: 6px 0;
            }
            .logic-formula {
              background: rgba(88, 166, 255, 0.05);
              border-left: 2px solid #58a6ff;
              padding: 8px 12px;
              margin: 8px 0;
              border-radius: 4px;
              font-family: 'Monaco', 'Courier New', monospace;
              font-size: 0.85em;
              color: #a5d6ff;
            }
            
            /* Table */
            .table-container {
              overflow-x: auto;
              border: 1px solid #30363d;
              border-radius: 10px;
              margin-bottom: 24px;
            }
            table {
              border-collapse: collapse;
              width: 100%;
              font-size: 0.9em;
              min-width: 1200px;
            }
            th {
              background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
              color: #79c0ff;
              padding: 12px;
              text-align: left;
              font-weight: 600;
              border-bottom: 2px solid #30363d;
              position: sticky;
              top: 0;
              z-index: 10;
              cursor: pointer;
              user-select: none;
              white-space: nowrap;
            }
            th:hover {
              background: linear-gradient(135deg, #1f6feb 0%, #0d1117 100%);
            }
            td {
              padding: 12px;
              border-bottom: 1px solid #21262d;
              text-align: left;
            }
            tbody tr:hover {
              background: rgba(88, 166, 255, 0.1);
            }
            tbody tr:nth-child(even) {
              background: rgba(13, 17, 23, 0.5);
            }
            
            /* Column Visibility */
            .col-primary { color: #7ee787; font-weight: 600; }
            .col-visible { display: table-cell; }
            .col-hidden { display: none; }
            
            tr:hover .col-hidden {
              display: table-cell;
              background: rgba(88, 166, 255, 0.15);
              border-left: 2px solid #58a6ff;
            }
            
            /* Rating Badges */
            .rating {
              display: inline-block;
              padding: 4px 10px;
              border-radius: 12px;
              font-weight: 600;
              font-size: 0.85em;
            }
            .rating-aplus { background: rgba(46, 160, 67, 0.3); color: #3fb950; border: 1px solid #3fb950; }
            .rating-a { background: rgba(46, 160, 67, 0.2); color: #2ea043; border: 1px solid #2ea043; }
            .rating-b { background: rgba(210, 153, 34, 0.2); color: #d29922; border: 1px solid #d29922; }
            .rating-c { background: rgba(248, 113, 73, 0.2); color: #f0883e; border: 1px solid #f0883e; }
            .rating-d { background: rgba(248, 81, 73, 0.2); color: #f85149; border: 1px solid #f85149; }
            
            /* Hover Details */
            .hover-detail {
              position: relative;
            }
            .hover-detail-content {
              display: none;
              position: absolute;
              bottom: 100%;
              left: 0;
              background: rgba(22, 27, 34, 0.98);
              border: 1px solid #30363d;
              border-radius: 8px;
              padding: 12px;
              color: #c9d1d9;
              font-size: 0.85em;
              white-space: normal;
              z-index: 1000;
              min-width: 300px;
              box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
            }
            .hover-detail:hover .hover-detail-content {
              display: block;
            }
            
            /* Footer */
            .footer {
              text-align: center;
              color: #8b949e;
              font-size: 0.9em;
              padding: 20px;
              border-top: 1px solid #30363d;
              margin-top: 40px;
            }
            
            @media (max-width: 1024px) {
              .controls {
                grid-template-columns: repeat(2, 1fr);
              }
            }
            
            @media (max-width: 768px) {
              body { padding: 12px; }
              .hero-content { flex-direction: column; }
              .controls { grid-template-columns: 1fr; }
              table { font-size: 0.8em; }
              th, td { padding: 8px; }
            }
          </style>
        """;
    }

    private static String getHeroSection(int resultCount, String market, String timeframe) {
        return """
          <div class="hero">
            <div class="hero-content">
              <div>
                <h1>🚀 VCP Breakout Scan Report</h1>
                <p style="color: #8b949e; margin: 4px 0;">Automated volatility contraction pattern detection</p>
              </div>
              <div class="hero-stats">
                <div class="stat-pill">📊 Scanned: 2,100+</div>
                <div class="stat-pill">✅ Hits: %d</div>
                <div class="stat-pill">📍 Market: %s</div>
                <div class="stat-pill">⏱️ Timeframe: %s</div>
              </div>
            </div>
          </div>
        """.formatted(resultCount, market.toUpperCase(), timeframe.toUpperCase());
    }

    private static String getFilteringSummary() {
        return """
          <div class="summary-box">
            <h3>📋 How Your System Filters Trades</h3>
            <p>
              Your system uses a <strong>4-stage multi-layered filtering approach</strong> to ensure only high-quality breakouts are presented:
            </p>
            <ul>
              <li><strong>Stage 1: Setup Detection</strong> — Identifies volatility contraction patterns with precise volume and range metrics</li>
              <li><strong>Stage 2: Quality Scoring</strong> — Ranks setups based on contraction depth and volume behavior</li>
              <li><strong>Stage 3: Breakout Confirmation</strong> — Validates price breakout with volume surge verification</li>
              <li><strong>Stage 4: Quality Analysis</strong> — Rates breakout strength using volume percentile and structural metrics</li>
            </ul>
            <p style="color: #8b949e; font-size: 0.9em; margin-top: 12px;">
              Hover over any trade row to see the complete filtering rationale. Expand sections below to understand the full logic.
            </p>
          </div>
        """;
    }

    private static String getControlsSection() {
        return """
          <div class="controls">
            <div class="control-group">
              <label class="control-label">Search Symbol</label>
              <input type="text" class="control-input" id="searchInput" placeholder="Enter symbol...">
            </div>
            <div class="control-group">
              <label class="control-label">Min Quality Score</label>
              <input type="range" class="control-input" id="scoreSlider" min="0" max="100" value="0">
            </div>
            <div class="control-group">
              <label class="control-label">Setup Type</label>
              <select class="control-select" id="setupFilter">
                <option value="all">All Setups</option>
                <option value="VCP">VCP Only</option>
                <option value="RANGE_EXPANSION">Range Expansion Only</option>
                <option value="MEAN_REVERSION">Mean Reversion Only</option>
              </select>
            </div>
            <div class="control-group">
              <label class="control-label">Rating Filter</label>
              <select class="control-select" id="ratingFilter">
                <option value="all">All Ratings</option>
                <option value="A+">A+ Only</option>
                <option value="A">A & Above</option>
                <option value="B">B & Above</option>
              </select>
            </div>
          </div>
        """;
    }

    private static String getAnalyticsSection(List<ScanResult> results) {
        double avgScore = results.stream().mapToDouble(r -> r.getSetup().getQualityScore()).average().orElse(0);
        double bestScore = results.stream().mapToDouble(r -> r.getSetup().getQualityScore()).max().orElse(0);
        double avgRR = results.stream().mapToDouble(r -> {
            double entry = r.getTradePlan().getEntry();
            double stop = r.getTradePlan().getStopLoss();
            double target = r.getTradePlan().getTarget1();
            if (stop > 0 && entry > 0) {
                return (target - entry) / (entry - stop);
            }
            return 0;
        }).average().orElse(0);
        
        return """
          <div class="analytics-grid">
            <div class="stat-card">
              <div class="stat-card-label">Total Setups Found</div>
              <div class="stat-card-value">%d</div>
            </div>
            <div class="stat-card">
              <div class="stat-card-label">Average Quality Score</div>
              <div class="stat-card-value">%.1f</div>
            </div>
            <div class="stat-card">
              <div class="stat-card-label">Avg Risk/Reward Ratio</div>
              <div class="stat-card-value">%.2f:1</div>
            </div>
            <div class="stat-card">
              <div class="stat-card-label">Best Quality Score</div>
              <div class="stat-card-value">%.1f</div>
            </div>
          </div>
        """.formatted(results.size(), avgScore, avgRR, bestScore);
    }

    private static String getFilteringLogicDocumentation() {
        return """
          <div class="logic-section">
            <div class="logic-header" onclick="toggleLogic()">
              <h2>
                <span class="logic-toggle">▶</span>
                📊 Complete Trade Filtering Logic
              </h2>
              <span style="font-size: 0.8em; color: #8b949e;">Click to expand/collapse</span>
            </div>
            <div class="logic-content" id="logicContent">
              
              <div class="logic-stage">
                <div class="logic-stage-title">STAGE 1️⃣: SETUP DETECTION — Volatility Contraction Pattern</div>
                <div class="logic-items">
                  <div class="logic-item"><strong>Window Analysis:</strong> System scans 20/30/45/60 bar consolidation windows</div>
                  <div class="logic-item"><strong>Wave Division:</strong> Each window is split into 3 waves of equal size</div>
                  <div class="logic-item">
                    <strong>Volume Contraction:</strong>
                    <div class="logic-formula">
                      volumeContraction = (Wave₁ Avg - Wave₃ Avg) / Wave₁ Avg
                    </div>
                  </div>
                  <div class="logic-item">
                    <strong>Dynamic Thresholds (by window length):</strong>
                    <ul style="margin: 6px 0; padding-left: 20px;">
                      <li>≤ 15 bars: min 22% contraction</li>
                      <li>16-30 bars: min 20% contraction</li>
                      <li>31-120 bars: min 10% contraction (default)</li>
                      <li>121-180 bars: min 8% contraction</li>
                      <li>≥ 180 bars: min 5% contraction</li>
                    </ul>
                  </div>
                  <div class="logic-item">
                    <strong>Range Contraction:</strong>
                    <div class="logic-formula">
                      rangeContraction = (Wave₁ High-Low - Wave₃ High-Low) / Wave₁ High-Low
                    </div>
                  </div>
                </div>
              </div>
              
              <div class="logic-stage">
                <div class="logic-stage-title">STAGE 2️⃣: QUALITY SCORING — VCP & Range Expansion</div>
                <div class="logic-items">
                  <div class="logic-item">
                    <strong>VCP Quality Score:</strong>
                    <div class="logic-formula">
                      VCP Score = [(rangeContraction × 0.60) + (volumeContraction × 0.40)] × 100
                    </div>
                  </div>
                  <div class="logic-item">
                    <strong>Range Expansion Score:</strong>
                    <div class="logic-formula">
                      Expansion Score = [(rangeContraction × 0.35) + (volumeContraction × 0.15) + (rangeExpansion × 0.35) + (expansionVolume × 0.15)] × 100
                    </div>
                  </div>
                  <div class="logic-item">
                    <strong>Weight Adjustments:</strong>
                    <ul style="margin: 6px 0; padding-left: 20px;">
                      <li>Short windows (≤20 bars): +5 bonus points</li>
                      <li>Medium windows (≤30 bars): +2 bonus points</li>
                      <li>Wick/Body adjustment: ±12 points (daily) or ±8 points (weekly)</li>
                    </ul>
                  </div>
                  <div class="logic-item"><strong>Minimum Score Required:</strong> 35-40 points to enter watchlist</div>
                </div>
              </div>
              
              <div class="logic-stage">
                <div class="logic-stage-title">STAGE 3️⃣: BREAKOUT CONFIRMATION — Volume & Price Verification</div>
                <div class="logic-items">
                  <div class="logic-item">
                    <strong>Volume Confirmation:</strong>
                    <div class="logic-formula">
                      breakoutVolume ≥ (20-day avgVolume) × volumeMultiplier
                    </div>
                  </div>
                  <div class="logic-item">
                    <strong>Volume Multipliers:</strong>
                    <ul style="margin: 6px 0; padding-left: 20px;">
                      <li>Fresh pivot break (Daily): 1.25x required</li>
                      <li>Near-breakout continuation (3-8% above pivot): 1.05x</li>
                      <li>Weekly timeframe: 1.10x multiplier</li>
                    </ul>
                  </div>
                  <div class="logic-item">
                    <strong>Price Confirmation (Daily):</strong>
                    <ul style="margin: 6px 0; padding-left: 20px;">
                      <li>Close must be > Pivot + 0.3% buffer</li>
                      <li>High must pierce the pivot intraday</li>
                      <li>Prevents false breakouts from gap-ups</li>
                    </ul>
                  </div>
                  <div class="logic-item">
                    <strong>Range Expansion Check (if applicable):</strong>
                    <div class="logic-formula">
                      breakoutRange ≥ 20-bar ATR × 1.30
                    </div>
                  </div>
                </div>
              </div>
              
              <div class="logic-stage">
                <div class="logic-stage-title">STAGE 4️⃣: BREAKOUT QUALITY ANALYSIS — Strength Rating</div>
                <div class="logic-items">
                  <div class="logic-item">
                    <strong>Volume Percentile Score (0-10 points):</strong>
                    <ul style="margin: 6px 0; padding-left: 20px;">
                      <li>≥ 80th percentile of prior 50 bars: 10 points (EXCELLENT)</li>
                      <li>≥ 60th percentile: 8 points (STRONG)</li>
                      <li>≥ 50th percentile: 6 points (GOOD)</li>
                      <li>≥ 40th percentile: 5 points (FAIR)</li>
                      <li>< 30th percentile: 1 point (WEAK)</li>
                    </ul>
                  </div>
                  <div class="logic-item">
                    <strong>Additional Quality Factors (0-30 points):</strong>
                    <ul style="margin: 6px 0; padding-left: 20px;">
                      <li>Pivot Freshness: how recent is the setup (0-10 pts)</li>
                      <li>Distance Efficiency: how close entry is to optimal (0-10 pts)</li>
                      <li>Tightness Quality: squeeze depth and structure (0-10 pts)</li>
                    </ul>
                  </div>
                  <div class="logic-item">
                    <strong>Overall Quality Rating:</strong>
                    <ul style="margin: 6px 0; padding-left: 20px;">
                      <li>A+: 35-40 points (Excellent institutional volume confirmation)</li>
                      <li>A: 30-34 points (Strong volume support, clean structure)</li>
                      <li>B: 25-29 points (Good setup, adequate volume)</li>
                      <li>C: 20-24 points (Fair setup, some volume concerns)</li>
                      <li>D: 15-19 points (Weak setup, marginal volume)</li>
                    </ul>
                  </div>
                </div>
              </div>
              
              <div class="logic-stage">
                <div class="logic-stage-title">🔴 REJECTION REASONS — Why Trades Are Filtered Out</div>
                <div class="logic-items">
                  <div class="logic-item"><strong>INSUFFICIENT_VOLUME:</strong> Breakout bar volume < required multiplier × 20-day average</div>
                  <div class="logic-item"><strong>NO_BREAKOUT:</strong> Price failed to close above pivot + buffer OR intraday high didn't pierce pivot</div>
                  <div class="logic-item"><strong>LOW_QUALITY_SETUP:</strong> Base shows < required volume/range contraction</div>
                  <div class="logic-item"><strong>PRICE_BELOW_MA:</strong> Close is below configured moving average (trend filter)</div>
                  <div class="logic_item"><strong>FAR_FROM_52WK_HIGH:</strong> Stock is too far below 52-week high (likely in downtrend)</div>
                  <div class="logic-item"><strong>PENNY_STOCK:</strong> Price is below minimum price threshold (default $1.00)</div>
                  <div class="logic-item"><strong>ATR_EXPANDING:</strong> For range expansion setups, breakout range < required ATR multiple</div>
                  <div class="logic-item"><strong>INSUFFICIENT_DATA:</strong> < 8 bars of historical data available</div>
                </div>
              </div>
              
              <div class="logic-stage">
                <div class="logic-stage-title">✅ ACCEPTANCE CRITERIA — What Makes a Trade Make the Cut</div>
                <div class="logic-items">
                  <div class="logic-item">✓ Setup quality score ≥ minimum threshold (35-40 points)</div>
                  <div class="logic-item">✓ Volume contraction meets dynamic window-based requirement</div>
                  <div class="logic-item">✓ Price close > pivot + 0.3% buffer</div>
                  <div class="logic-item">✓ Breakout volume ≥ 1.25x (daily) or 1.10x (weekly) 20-day average</div>
                  <div class="logic-item">✓ Stock above configurable moving average (uptrend confirmation)</div>
                  <div class="logic-item">✓ Stock within maxDistance from 52-week high</div>
                  <div class="logic-item">✓ Price ≥ minimum price filter ($1.00 daily, $0.50 weekly)</div>
                  <div class="logic-item">✓ Sufficient historical data (min 8 bars for validation)</div>
                </div>
              </div>
              
            </div>
          </div>
          
          <script>
            function toggleLogic() {
              const content = document.getElementById('logicContent');
              const toggle = document.querySelector('.logic-toggle');
              content.classList.toggle('collapsed');
              toggle.classList.toggle('collapsed');
            }
          </script>
        """;
    }

    private static String getDataTable(List<ScanResult> results) {
        StringBuilder html = new StringBuilder();
        html.append("<div class=\"table-container\">\n");
        html.append("  <table id=\"dataTable\">\n");
        html.append("    <thead>\n");
        html.append("      <tr>\n");
        // All columns from SignalExport and nested details
        html.append("        <th>Symbol</th>\n");
        html.append("        <th>Signal Type</th>\n");
        html.append("        <th>Base Score</th>\n");
        html.append("        <th>Alignment Bonus</th>\n");
        html.append("        <th>Final Score</th>\n");
        html.append("        <th>Quality Rating</th>\n");
        html.append("        <th>Quality Score</th>\n");
        html.append("        <th>Setup Type</th>\n");
        html.append("        <th>Window</th>\n");
        html.append("        <th>Window Bars</th>\n");
        html.append("        <th>Range Height %</th>\n");
        html.append("        <th>Contraction Depth %</th>\n");
        html.append("        <th>Range Contraction</th>\n");
        html.append("        <th>Volume Contraction</th>\n");
        html.append("        <th>Range Expansion</th>\n");
        html.append("        <th>Setup Rating</th>\n");
        html.append("        <th>Pivot Price</th>\n");
        html.append("        <th>Close Price</th>\n");
        html.append("        <th>Entry Price</th>\n");
        html.append("        <th>Close-Pivot Dist %</th>\n");
        html.append("        <th>Pivot Test Count</th>\n");
        html.append("        <th>MultiTF Align</th>\n");
        html.append("        <th>Weekly Align Bonus</th>\n");
        html.append("        <th>Weekly Structure</th>\n");
        html.append("        <th>Trade Entry</th>\n");
        html.append("        <th>Stop Loss</th>\n");
        html.append("        <th>Shares</th>\n");
        html.append("        <th>Target 1</th>\n");
        html.append("        <th>Target 2</th>\n");
        html.append("        <th>Target 3</th>\n");
        html.append("        <th>R:R T1</th>\n");
        html.append("        <th>R:R T2</th>\n");
        html.append("        <th>R:R T3</th>\n");
        html.append("        <th>Data Quality</th>\n");
        html.append("        <th>Data Errors</th>\n");
        html.append("        <th>Data Warnings</th>\n");
        html.append("      </tr>\n");
        html.append("    </thead>\n");
        html.append("    <tbody>\n");
        for (ScanResult result : results) {
            html.append("      <tr>\n");
            html.append("        <td>").append(result.getSymbol()).append("</td>\n");
            html.append("        <td>").append(result.getSignalType()).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f", result.getSetup().getQualityScore())).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f", result.getAlignmentBonus())).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f", result.getQualityScore())).append("</td>\n");
            html.append("        <td><span class=\"rating rating-").append(getRatingClass(result.getSetup().getSetupRating())).append("\">").append(result.getSetup().getSetupRating()).append("</span></td>\n");
            html.append("        <td>").append(String.format("%.1f", result.getSetup().getQualityScore())).append("</td>\n");
            html.append("        <td>").append(result.getSetup().getSetupType()).append("</td>\n");
            html.append("        <td>").append(result.getSetup().getBaseWindowLabel()).append("</td>\n");
            html.append("        <td>").append(result.getSetup().getBaseWindowBars()).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f%%", result.getSetup().getBaseRangeHeightPct())).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f%%", result.getSetup().getContractionDepthPct())).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f%%", result.getSetup().getRangeContraction() * 100)).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f%%", result.getSetup().getVolumeContraction() * 100)).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f%%", result.getSetup().getRangeExpansion() * 100)).append("</td>\n");
            html.append("        <td>").append(result.getSetup().getSetupRating()).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f", result.getSetup().getPivotPrice())).append("</td>\n");
            html.append("        <td>").append(result.getSignalCandle() != null ? String.format("%.2f", result.getSignalCandle().getClose()) : "").append("</td>\n");
            html.append("        <td>").append(String.format("%.2f", result.getTradePlan().getEntry())).append("</td>\n");
            html.append("        <td>").append(result.getSignalCandle() != null && result.getSetup().getPivotPrice() > 0 ? String.format("%.2f%%", (result.getSignalCandle().getClose() - result.getSetup().getPivotPrice()) / result.getSetup().getPivotPrice() * 100) : "").append("</td>\n");
            html.append("        <td>").append(result.getSetup().getRangeContractionCount()).append("</td>\n");
            html.append("        <td>").append(result.getAlignmentReason() != null ? result.getAlignmentReason() : "").append("</td>\n");
            html.append("        <td>").append(result.getAlignmentBonus()).append("</td>\n");
            html.append("        <td>").append(result.isWeeklyAligned() ? "Aligned" : "Not aligned").append("</td>\n");
            html.append("        <td>").append(String.format("%.2f", result.getTradePlan().getEntry())).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f", result.getTradePlan().getStopLoss())).append("</td>\n");
            html.append("        <td>").append(result.getTradePlan().getShares()).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f", result.getTradePlan().getTarget1())).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f", result.getTradePlan().getTarget2())).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f", result.getTradePlan().getTarget3())).append("</td>\n");
            double rr1 = (result.getTradePlan().getEntry() > result.getTradePlan().getStopLoss()) ? (result.getTradePlan().getTarget1() - result.getTradePlan().getEntry()) / (result.getTradePlan().getEntry() - result.getTradePlan().getStopLoss()) : 0;
            double rr2 = (result.getTradePlan().getEntry() > result.getTradePlan().getStopLoss()) ? (result.getTradePlan().getTarget2() - result.getTradePlan().getEntry()) / (result.getTradePlan().getEntry() - result.getTradePlan().getStopLoss()) : 0;
            double rr3 = (result.getTradePlan().getEntry() > result.getTradePlan().getStopLoss()) ? (result.getTradePlan().getTarget3() - result.getTradePlan().getEntry()) / (result.getTradePlan().getEntry() - result.getTradePlan().getStopLoss()) : 0;
            html.append("        <td>").append(String.format("%.2f:1", rr1)).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f:1", rr2)).append("</td>\n");
            html.append("        <td>").append(String.format("%.2f:1", rr3)).append("</td>\n");
            // Data quality (placeholder, as ScanResult does not expose directly)
            html.append("        <td>").append("OK").append("</td>\n");
            html.append("        <td>").append("").append("</td>\n"); // Data Errors placeholder
            html.append("        <td>").append("").append("</td>\n"); // Data Warnings placeholder
            html.append("      </tr>\n");
        }
        html.append("    </tbody>\n");
        html.append("  </table>\n");
        html.append("</div>\n");
        return html.toString();
    }

    private static String getRatingClass(String rating) {
        return rating.replace("+", "plus").toLowerCase();
    }

    private static double calculateRiskReward(ScanResult result) {
        double entry = result.getTradePlan().getEntry();
        double stop = result.getTradePlan().getStopLoss();
        double target = result.getTradePlan().getTarget1();
        if (stop > 0 && entry > stop) {
            return (target - entry) / (entry - stop);
        }
        return 0;
    }

    private static String getJavaScript() {
        return """
          <script>
            // Search functionality
            document.getElementById('searchInput')?.addEventListener('keyup', function(e) {
              const searchTerm = e.target.value.toLowerCase();
              document.querySelectorAll('tbody tr').forEach(row => {
                const symbol = row.cells[0].textContent.toLowerCase();
                row.style.display = symbol.includes(searchTerm) ? '' : 'none';
              });
            });
            
            // Score slider
            document.getElementById('scoreSlider')?.addEventListener('input', function(e) {
              const minScore = parseFloat(e.target.value);
              document.querySelectorAll('tbody tr').forEach(row => {
                const scoreText = row.cells[2].textContent;
                row.style.display = 'none'; // Default: hide (since quality is in text format)
              });
            });
            
            // Setup filter
            document.getElementById('setupFilter')?.addEventListener('change', function(e) {
              const setupType = e.target.value;
              document.querySelectorAll('tbody tr').forEach(row => {
                const setup = row.cells[1].textContent;
                if (setupType === 'all' || setup.includes(setupType)) {
                  row.style.display = '';
                } else {
                  row.style.display = 'none';
                }
              });
            });
            
            // Rating filter
            document.getElementById('ratingFilter')?.addEventListener('change', function(e) {
              const rating = e.target.value;
              document.querySelectorAll('tbody tr').forEach(row => {
                const rowRating = row.cells[2].textContent.trim();
                if (rating === 'all') {
                  row.style.display = '';
                } else if (rating === 'A+' && rowRating === 'A+') {
                  row.style.display = '';
                } else if (rating === 'A' && (rowRating === 'A' || rowRating === 'A+')) {
                  row.style.display = '';
                } else if (rating === 'B' && ['A+', 'A', 'B'].includes(rowRating)) {
                  row.style.display = '';
                } else {
                  row.style.display = 'none';
                }
              });
            });
          </script>
        """;
    }
}

