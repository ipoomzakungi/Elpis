const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

import {
  ApiResponse,
  BacktestEquityResponse,
  BacktestMetricsResponse,
  BacktestRun,
  BacktestRunListResponse,
  BacktestTradesResponse,
  DataQualityResponse,
  DataSourceCapabilityListResponse,
  DataSourceMissingDataResponse,
  DataSourceReadiness,
  DownloadRequest,
  Feature,
  FundingRate,
  MarketData,
  OpenInterest,
  ProviderDownloadRequest,
  ProviderDownloadResult,
  ProviderInfo,
  ProviderSymbolsResponse,
  ProvidersResponse,
  ProcessRequest,
  Regime,
  ResearchAssetSummaryResponse,
  ResearchComparisonResponse,
  ResearchDashboardData,
  ResearchExecutionDashboardData,
  ResearchEvidenceSummary,
  ResearchExecutionMissingDataResponse,
  ResearchExecutionRun,
  ResearchExecutionRunListResponse,
  ResearchExecutionRunRequest,
  ResearchRun,
  ResearchRunListResponse,
  ResearchRunRequest,
  ResearchValidationAggregationResponse,
  TaskResponse,
  ValidationConcentrationResponse,
  ValidationRun,
  ValidationRunListResponse,
  ValidationRunRequest,
  ValidationSensitivityResponse,
  ValidationStressResponse,
  ValidationWalkForwardResponse,
  XauVolOiReport,
  XauDashboardData,
  XauVolOiReportListResponse,
  XauVolOiReportRequest,
  XauWallTableResponse,
  XauZoneTableResponse,
} from '@/types';

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: response.statusText }));
    throw new Error(error.error?.message || error.message || `API error: ${response.status}`);
  }

  return response.json();
}

export const api = {
  // Download data
  download: async (request: DownloadRequest = {}): Promise<TaskResponse> => {
    return fetchApi('/download', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  // Process data
  process: async (request: ProcessRequest = {}): Promise<TaskResponse> => {
    return fetchApi('/process', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  // Market data
  getOHLCV: async (params?: {
    symbol?: string;
    interval?: string;
    start_time?: string;
    end_time?: string;
    limit?: number;
  }): Promise<ApiResponse<MarketData>> => {
    const query = new URLSearchParams(params as Record<string, string>);
    return fetchApi(`/market-data/ohlcv?${query}`);
  },

  getOpenInterest: async (params?: {
    symbol?: string;
    interval?: string;
    start_time?: string;
    end_time?: string;
    limit?: number;
  }): Promise<ApiResponse<OpenInterest>> => {
    const query = new URLSearchParams(params as Record<string, string>);
    return fetchApi(`/market-data/open-interest?${query}`);
  },

  getFundingRate: async (params?: {
    symbol?: string;
    start_time?: string;
    end_time?: string;
    limit?: number;
  }): Promise<ApiResponse<FundingRate>> => {
    const query = new URLSearchParams(params as Record<string, string>);
    return fetchApi(`/market-data/funding-rate?${query}`);
  },

  // Features
  getFeatures: async (params?: {
    symbol?: string;
    interval?: string;
    start_time?: string;
    end_time?: string;
    limit?: number;
  }): Promise<ApiResponse<Feature>> => {
    const query = new URLSearchParams(params as Record<string, string>);
    return fetchApi(`/features?${query}`);
  },

  // Regimes
  getRegimes: async (params?: {
    symbol?: string;
    interval?: string;
    start_time?: string;
    end_time?: string;
    regime?: string;
    limit?: number;
  }): Promise<ApiResponse<Regime>> => {
    const query = new URLSearchParams(params as Record<string, string>);
    return fetchApi(`/regimes?${query}`);
  },

  // Data quality
  getDataQuality: async (symbol?: string): Promise<DataQualityResponse> => {
    const query = symbol ? `?symbol=${symbol}` : '';
    return fetchApi(`/data-quality${query}`);
  },

  // Providers
  getProviders: async (): Promise<ProvidersResponse> => {
    return fetchApi('/providers');
  },

  getProvider: async (providerName: string): Promise<ProviderInfo> => {
    return fetchApi(`/providers/${providerName}`);
  },

  getProviderSymbols: async (providerName: string): Promise<ProviderSymbolsResponse> => {
    return fetchApi(`/providers/${providerName}/symbols`);
  },

  downloadProvider: async (request: ProviderDownloadRequest): Promise<ProviderDownloadResult> => {
    return fetchApi('/data/download', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  // Data-source onboarding
  getDataSourceReadiness: async (): Promise<DataSourceReadiness> => {
    return fetchApi('/data-sources/readiness');
  },

  getDataSourceCapabilities: async (): Promise<DataSourceCapabilityListResponse> => {
    return fetchApi('/data-sources/capabilities');
  },

  getDataSourceMissingData: async (): Promise<DataSourceMissingDataResponse> => {
    return fetchApi('/data-sources/missing-data');
  },

  // Backtest reports
  getBacktests: async (): Promise<BacktestRunListResponse> => {
    return fetchApi('/backtests');
  },

  getBacktestRun: async (runId: string): Promise<BacktestRun> => {
    return fetchApi(`/backtests/${encodeURIComponent(runId)}`);
  },

  getBacktestTrades: async (
    runId: string,
    params: { limit?: number; offset?: number } = {},
  ): Promise<BacktestTradesResponse> => {
    const query = new URLSearchParams();
    if (params.limit !== undefined) query.set('limit', String(params.limit));
    if (params.offset !== undefined) query.set('offset', String(params.offset));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    return fetchApi(`/backtests/${encodeURIComponent(runId)}/trades${suffix}`);
  },

  getBacktestMetrics: async (runId: string): Promise<BacktestMetricsResponse> => {
    return fetchApi(`/backtests/${encodeURIComponent(runId)}/metrics`);
  },

  getBacktestEquity: async (runId: string): Promise<BacktestEquityResponse> => {
    return fetchApi(`/backtests/${encodeURIComponent(runId)}/equity`);
  },

  // Validation report stress and sensitivity sections
  getValidationReports: async (): Promise<ValidationRunListResponse> => {
    return fetchApi('/backtests/validation');
  },

  runValidationReport: async (request: ValidationRunRequest): Promise<ValidationRun> => {
    return fetchApi('/backtests/validation/run', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  getValidationReport: async (validationRunId: string): Promise<ValidationRun> => {
    return fetchApi(`/backtests/validation/${encodeURIComponent(validationRunId)}`);
  },

  getValidationStress: async (validationRunId: string): Promise<ValidationStressResponse> => {
    return fetchApi(`/backtests/validation/${encodeURIComponent(validationRunId)}/stress`);
  },

  getValidationSensitivity: async (
    validationRunId: string,
  ): Promise<ValidationSensitivityResponse> => {
    return fetchApi(`/backtests/validation/${encodeURIComponent(validationRunId)}/sensitivity`);
  },

  getValidationWalkForward: async (
    validationRunId: string,
  ): Promise<ValidationWalkForwardResponse> => {
    return fetchApi(`/backtests/validation/${encodeURIComponent(validationRunId)}/walk-forward`);
  },

  getValidationConcentration: async (
    validationRunId: string,
  ): Promise<ValidationConcentrationResponse> => {
    return fetchApi(`/backtests/validation/${encodeURIComponent(validationRunId)}/concentration`);
  },

  // Multi-asset research reports
  runResearchReport: async (request: ResearchRunRequest): Promise<ResearchRun> => {
    return fetchApi('/research/runs', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  getResearchReports: async (): Promise<ResearchRunListResponse> => {
    return fetchApi('/research/runs');
  },

  getResearchReport: async (researchRunId: string): Promise<ResearchRun> => {
    return fetchApi(`/research/runs/${encodeURIComponent(researchRunId)}`);
  },

  getResearchAssets: async (
    researchRunId: string,
  ): Promise<ResearchAssetSummaryResponse> => {
    return fetchApi(`/research/runs/${encodeURIComponent(researchRunId)}/assets`);
  },

  getResearchComparison: async (
    researchRunId: string,
  ): Promise<ResearchComparisonResponse> => {
    return fetchApi(`/research/runs/${encodeURIComponent(researchRunId)}/comparison`);
  },

  getResearchValidation: async (
    researchRunId: string,
  ): Promise<ResearchValidationAggregationResponse> => {
    return fetchApi(`/research/runs/${encodeURIComponent(researchRunId)}/validation`);
  },

  getResearchDashboardData: async (researchRunId: string): Promise<ResearchDashboardData> => {
    const encodedRunId = encodeURIComponent(researchRunId);
    const [run, assets, comparison, validation] = await Promise.all([
      fetchApi<ResearchRun>(`/research/runs/${encodedRunId}`),
      fetchApi<ResearchAssetSummaryResponse>(`/research/runs/${encodedRunId}/assets`),
      fetchApi<ResearchComparisonResponse>(`/research/runs/${encodedRunId}/comparison`),
      fetchApi<ResearchValidationAggregationResponse>(
        `/research/runs/${encodedRunId}/validation`,
      ),
    ]);
    return { run, assets, comparison, validation };
  },

  // Research execution evidence reports
  runResearchExecution: async (
    request: ResearchExecutionRunRequest,
  ): Promise<ResearchExecutionRun> => {
    return fetchApi('/research/execution-runs', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  getResearchExecutionRuns: async (): Promise<ResearchExecutionRunListResponse> => {
    return fetchApi('/research/execution-runs');
  },

  getResearchExecutionRun: async (
    executionRunId: string,
  ): Promise<ResearchExecutionRun> => {
    return fetchApi(`/research/execution-runs/${encodeURIComponent(executionRunId)}`);
  },

  getResearchExecutionEvidence: async (
    executionRunId: string,
  ): Promise<ResearchEvidenceSummary> => {
    return fetchApi(`/research/execution-runs/${encodeURIComponent(executionRunId)}/evidence`);
  },

  getResearchExecutionMissingData: async (
    executionRunId: string,
  ): Promise<ResearchExecutionMissingDataResponse> => {
    return fetchApi(
      `/research/execution-runs/${encodeURIComponent(executionRunId)}/missing-data`,
    );
  },

  getResearchExecutionDashboardData: async (
    executionRunId: string,
  ): Promise<ResearchExecutionDashboardData> => {
    const encodedRunId = encodeURIComponent(executionRunId);
    const [run, evidence, missingData] = await Promise.all([
      fetchApi<ResearchExecutionRun>(`/research/execution-runs/${encodedRunId}`),
      fetchApi<ResearchEvidenceSummary>(`/research/execution-runs/${encodedRunId}/evidence`),
      fetchApi<ResearchExecutionMissingDataResponse>(
        `/research/execution-runs/${encodedRunId}/missing-data`,
      ),
    ]);
    const statusCounts = evidence.workflow_results.reduce(
      (counts, workflow) => ({
        ...counts,
        [workflow.status]: counts[workflow.status] + 1,
      }),
      { completed: 0, partial: 0, blocked: 0, skipped: 0, failed: 0 },
    );
    return { run, evidence, missingData, statusCounts };
  },

  // XAU Vol-OI reports
  runXauVolOiReport: async (request: XauVolOiReportRequest): Promise<XauVolOiReport> => {
    return fetchApi('/xau/vol-oi/reports', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  getXauVolOiReports: async (): Promise<XauVolOiReportListResponse> => {
    return fetchApi('/xau/vol-oi/reports');
  },

  getXauVolOiReport: async (reportId: string): Promise<XauVolOiReport> => {
    return fetchApi(`/xau/vol-oi/reports/${encodeURIComponent(reportId)}`);
  },

  getXauVolOiWalls: async (reportId: string): Promise<XauWallTableResponse> => {
    return fetchApi(`/xau/vol-oi/reports/${encodeURIComponent(reportId)}/walls`);
  },

  getXauVolOiZones: async (reportId: string): Promise<XauZoneTableResponse> => {
    return fetchApi(`/xau/vol-oi/reports/${encodeURIComponent(reportId)}/zones`);
  },

  getXauVolOiDashboardData: async (reportId: string): Promise<XauDashboardData> => {
    const encodedReportId = encodeURIComponent(reportId);
    const [report, walls, zones] = await Promise.all([
      fetchApi<XauVolOiReport>(`/xau/vol-oi/reports/${encodedReportId}`),
      fetchApi<XauWallTableResponse>(`/xau/vol-oi/reports/${encodedReportId}/walls`),
      fetchApi<XauZoneTableResponse>(`/xau/vol-oi/reports/${encodedReportId}/zones`),
    ]);
    return { report, walls, zones };
  },
};
