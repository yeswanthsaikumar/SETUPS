import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Loads sector/industry taxonomy and computes sector-level RS rankings.
 * Stocks in top-performing sectors get a score bonus; bottom sectors get filtered.
 *
 * Taxonomy source: data/nse_stock_taxonomy.csv
 * Format: nse_ticker,sector,industry,notes
 */
public class SectorStrengthAnalyzer {
    private final Map<String, String> symbolToSector;
    private final Map<String, String> symbolToIndustry;

    public SectorStrengthAnalyzer() {
        this.symbolToSector = new HashMap<>();
        this.symbolToIndustry = new HashMap<>();
    }

    public void loadTaxonomy(String taxonomyPath) {
        try {
            List<String> lines = Files.readAllLines(Paths.get(taxonomyPath));
            boolean header = true;
            for (String line : lines) {
                if (header) { header = false; continue; }
                String[] parts = line.split(",", -1);
                if (parts.length >= 3) {
                    String ticker = parts[0].trim();
                    String sector = parts[1].trim();
                    String industry = parts[2].trim();
                    if (!ticker.isEmpty() && !sector.isEmpty()) {
                        symbolToSector.put(ticker, sector);
                        symbolToIndustry.put(ticker, industry);
                        symbolToSector.put(ticker + ".NS", sector);
                        symbolToIndustry.put(ticker + ".NS", industry);
                    }
                }
            }
        } catch (IOException ex) {
            System.err.println("Could not load taxonomy: " + ex.getMessage());
        }
    }

    public String getSector(String symbol) {
        return symbolToSector.get(symbol);
    }

    public String getIndustry(String symbol) {
        return symbolToIndustry.get(symbol);
    }

    public Map<String, Double> computeSectorStrength(Map<String, RelativeStrengthCalculator.RSProfile> rsProfiles) {
        Map<String, List<Double>> sectorScores = new HashMap<>();
        for (Map.Entry<String, RelativeStrengthCalculator.RSProfile> entry : rsProfiles.entrySet()) {
            String sector = symbolToSector.get(entry.getKey());
            if (sector == null || sector.isEmpty()) continue;
            sectorScores.computeIfAbsent(sector, k -> new ArrayList<>()).add(entry.getValue().percentileRank);
        }
        Map<String, Double> result = new HashMap<>();
        for (Map.Entry<String, List<Double>> entry : sectorScores.entrySet()) {
            List<Double> scores = entry.getValue();
            double avg = scores.stream().mapToDouble(d -> d).average().orElse(50.0);
            result.put(entry.getKey(), avg);
        }
        return result;
    }

    public Map<String, Double> computeIndustryStrength(Map<String, RelativeStrengthCalculator.RSProfile> rsProfiles) {
        Map<String, List<Double>> industryScores = new HashMap<>();
        for (Map.Entry<String, RelativeStrengthCalculator.RSProfile> entry : rsProfiles.entrySet()) {
            String industry = symbolToIndustry.get(entry.getKey());
            if (industry == null || industry.isEmpty()) continue;
            industryScores.computeIfAbsent(industry, k -> new ArrayList<>()).add(entry.getValue().percentileRank);
        }
        Map<String, Double> result = new HashMap<>();
        for (Map.Entry<String, List<Double>> entry : industryScores.entrySet()) {
            List<Double> scores = entry.getValue();
            double avg = scores.stream().mapToDouble(d -> d).average().orElse(50.0);
            result.put(entry.getKey(), avg);
        }
        return result;
    }

    public double sectorScoreAdjustment(String symbol, Map<String, Double> sectorStrength) {
        String sector = symbolToSector.get(symbol);
        if (sector == null || !sectorStrength.containsKey(sector)) return 0.0;
        double sectorRank = sectorStrength.get(sector);
        if (sectorRank >= 80.0) return 10.0;
        if (sectorRank >= 60.0) return 5.0;
        if (sectorRank <= 20.0) return -5.0;
        return 0.0;
    }

    public boolean isWeakSector(String symbol, Map<String, Double> sectorStrength) {
        String sector = symbolToSector.get(symbol);
        if (sector == null || !sectorStrength.containsKey(sector)) return false;
        return sectorStrength.get(sector) <= 25.0;
    }

    public boolean hasTaxonomy() {
        return !symbolToSector.isEmpty();
    }
}

