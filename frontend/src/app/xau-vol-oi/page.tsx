'use client'

import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { api } from '@/services/api'
import {
  QuikStrikeDashboardData,
  QuikStrikeExtractionSummary,
  QuikStrikeMatrixDashboardData,
  QuikStrikeMatrixExtractionSummary,
  XauDashboardData,
  XauAcceptanceResult,
  XauExpectedRange,
  XauFreshnessResult,
  XauOiWall,
  XauOpenRegimeResult,
  XauReactionDashboardData,
  XauReactionReportSummary,
  XauReactionRow,
  XauRiskPlan,
  XauQuikStrikeFusionDashboardData,
  XauQuikStrikeFusionSummary,
  XauVolRegimeResult,
  XauVolOiReportSummary,
  XauZone,
} from '@/types'

export default function XauVolOiPage() {
  const [reports, setReports] = useState<XauVolOiReportSummary[]>([])
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)
  const [dashboardData, setDashboardData] = useState<XauDashboardData | null>(null)
  const [reactionReports, setReactionReports] = useState<XauReactionReportSummary[]>([])
  const [selectedReactionReportId, setSelectedReactionReportId] = useState<string | null>(null)
  const [reactionData, setReactionData] = useState<XauReactionDashboardData | null>(null)
  const [quikStrikeReports, setQuikStrikeReports] = useState<QuikStrikeExtractionSummary[]>([])
  const [selectedQuikStrikeId, setSelectedQuikStrikeId] = useState<string | null>(null)
  const [quikStrikeData, setQuikStrikeData] = useState<QuikStrikeDashboardData | null>(null)
  const [quikStrikeMatrixReports, setQuikStrikeMatrixReports] = useState<
    QuikStrikeMatrixExtractionSummary[]
  >([])
  const [selectedQuikStrikeMatrixId, setSelectedQuikStrikeMatrixId] = useState<string | null>(null)
  const [quikStrikeMatrixData, setQuikStrikeMatrixData] =
    useState<QuikStrikeMatrixDashboardData | null>(null)
  const [fusionReports, setFusionReports] = useState<XauQuikStrikeFusionSummary[]>([])
  const [selectedFusionReportId, setSelectedFusionReportId] = useState<string | null>(null)
  const [fusionData, setFusionData] = useState<XauQuikStrikeFusionDashboardData | null>(null)
  const [loadingReports, setLoadingReports] = useState(true)
  const [loadingReport, setLoadingReport] = useState(false)
  const [loadingReactionReports, setLoadingReactionReports] = useState(true)
  const [loadingReactionReport, setLoadingReactionReport] = useState(false)
  const [loadingQuikStrikeReports, setLoadingQuikStrikeReports] = useState(true)
  const [loadingQuikStrikeReport, setLoadingQuikStrikeReport] = useState(false)
  const [loadingQuikStrikeMatrixReports, setLoadingQuikStrikeMatrixReports] = useState(true)
  const [loadingQuikStrikeMatrixReport, setLoadingQuikStrikeMatrixReport] = useState(false)
  const [loadingFusionReports, setLoadingFusionReports] = useState(true)
  const [loadingFusionReport, setLoadingFusionReport] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reactionError, setReactionError] = useState<string | null>(null)
  const [quikStrikeError, setQuikStrikeError] = useState<string | null>(null)
  const [quikStrikeMatrixError, setQuikStrikeMatrixError] = useState<string | null>(null)
  const [fusionError, setFusionError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoadingReports(true)
    api.getXauVolOiReports()
      .then((response) => {
        if (!active) return
        setReports(response.reports)
        setSelectedReportId((current) => current ?? response.reports[0]?.report_id ?? null)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'XAU reports could not be loaded')
      })
      .finally(() => {
        if (active) setLoadingReports(false)
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    setLoadingReactionReports(true)
    api.listXauReactionReports()
      .then((response) => {
        if (!active) return
        setReactionReports(response.reports)
      })
      .catch((err) => {
        if (!active) return
        setReactionError(
          err instanceof Error ? err.message : 'XAU reaction reports could not be loaded',
        )
      })
      .finally(() => {
        if (active) setLoadingReactionReports(false)
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    setLoadingQuikStrikeReports(true)
    api.listQuikStrikeExtractions()
      .then((response) => {
        if (!active) return
        setQuikStrikeReports(response.extractions)
        setSelectedQuikStrikeId((current) => current ?? response.extractions[0]?.extraction_id ?? null)
      })
      .catch((err) => {
        if (!active) return
        setQuikStrikeError(
          err instanceof Error ? err.message : 'QuikStrike extraction reports could not be loaded',
        )
      })
      .finally(() => {
        if (active) setLoadingQuikStrikeReports(false)
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    setLoadingQuikStrikeMatrixReports(true)
    api.listQuikStrikeMatrixExtractions()
      .then((response) => {
        if (!active) return
        setQuikStrikeMatrixReports(response.extractions)
        setSelectedQuikStrikeMatrixId(
          (current) => current ?? response.extractions[0]?.extraction_id ?? null,
        )
      })
      .catch((err) => {
        if (!active) return
        setQuikStrikeMatrixError(
          err instanceof Error
            ? err.message
            : 'QuikStrike Matrix extraction reports could not be loaded',
        )
      })
      .finally(() => {
        if (active) setLoadingQuikStrikeMatrixReports(false)
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    setLoadingFusionReports(true)
    api.listXauQuikStrikeFusionReports()
      .then((response) => {
        if (!active) return
        setFusionReports(response.reports)
        setSelectedFusionReportId((current) => current ?? response.reports[0]?.report_id ?? null)
      })
      .catch((err) => {
        if (!active) return
        setFusionError(
          err instanceof Error ? err.message : 'XAU QuikStrike fusion reports could not be loaded',
        )
      })
      .finally(() => {
        if (active) setLoadingFusionReports(false)
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!selectedReportId) {
      setDashboardData(null)
      return
    }

    let active = true
    setLoadingReport(true)
    setError(null)
    api.getXauVolOiDashboardData(selectedReportId)
      .then((response) => {
        if (!active) return
        setDashboardData(response)
      })
      .catch((err) => {
        if (!active) return
        setDashboardData(null)
        setError(err instanceof Error ? err.message : 'XAU report could not be loaded')
      })
      .finally(() => {
        if (active) setLoadingReport(false)
      })

    return () => {
      active = false
    }
  }, [selectedReportId])

  useEffect(() => {
    if (!selectedFusionReportId) {
      setFusionData(null)
      return
    }

    let active = true
    setLoadingFusionReport(true)
    setFusionError(null)
    api.getXauQuikStrikeFusionDashboardData(selectedFusionReportId)
      .then((response) => {
        if (!active) return
        setFusionData(response)
      })
      .catch((err) => {
        if (!active) return
        setFusionData(null)
        setFusionError(
          err instanceof Error ? err.message : 'XAU QuikStrike fusion report could not be loaded',
        )
      })
      .finally(() => {
        if (active) setLoadingFusionReport(false)
      })

    return () => {
      active = false
    }
  }, [selectedFusionReportId])

  useEffect(() => {
    if (reactionReports.length === 0) {
      setSelectedReactionReportId(null)
      return
    }

    setSelectedReactionReportId((current) => {
      const currentSummary = reactionReports.find((item) => item.report_id === current)
      if (
        current &&
        currentSummary &&
        (!selectedReportId || currentSummary.source_report_id === selectedReportId)
      ) {
        return current
      }
      const sourceMatch = reactionReports.find((item) => item.source_report_id === selectedReportId)
      return sourceMatch?.report_id ?? reactionReports[0].report_id
    })
  }, [reactionReports, selectedReportId])

  useEffect(() => {
    if (!selectedReactionReportId) {
      setReactionData(null)
      return
    }

    let active = true
    setLoadingReactionReport(true)
    setReactionError(null)
    api.getXauReactionDashboardData(selectedReactionReportId)
      .then((response) => {
        if (!active) return
        setReactionData(response)
      })
      .catch((err) => {
        if (!active) return
        setReactionData(null)
        setReactionError(
          err instanceof Error ? err.message : 'XAU reaction report could not be loaded',
        )
      })
      .finally(() => {
        if (active) setLoadingReactionReport(false)
      })

    return () => {
      active = false
    }
  }, [selectedReactionReportId])

  useEffect(() => {
    if (!selectedQuikStrikeId) {
      setQuikStrikeData(null)
      return
    }

    let active = true
    setLoadingQuikStrikeReport(true)
    setQuikStrikeError(null)
    api.getQuikStrikeDashboardData(selectedQuikStrikeId)
      .then((response) => {
        if (!active) return
        setQuikStrikeData(response)
      })
      .catch((err) => {
        if (!active) return
        setQuikStrikeData(null)
        setQuikStrikeError(
          err instanceof Error ? err.message : 'QuikStrike extraction report could not be loaded',
        )
      })
      .finally(() => {
        if (active) setLoadingQuikStrikeReport(false)
      })

    return () => {
      active = false
    }
  }, [selectedQuikStrikeId])

  useEffect(() => {
    if (!selectedQuikStrikeMatrixId) {
      setQuikStrikeMatrixData(null)
      return
    }

    let active = true
    setLoadingQuikStrikeMatrixReport(true)
    setQuikStrikeMatrixError(null)
    api.getQuikStrikeMatrixDashboardData(selectedQuikStrikeMatrixId)
      .then((response) => {
        if (!active) return
        setQuikStrikeMatrixData(response)
      })
      .catch((err) => {
        if (!active) return
        setQuikStrikeMatrixData(null)
        setQuikStrikeMatrixError(
          err instanceof Error
            ? err.message
            : 'QuikStrike Matrix extraction report could not be loaded',
        )
      })
      .finally(() => {
        if (active) setLoadingQuikStrikeMatrixReport(false)
      })

    return () => {
      active = false
    }
  }, [selectedQuikStrikeMatrixId])

  const selectedSummary = useMemo(
    () => reports.find((item) => item.report_id === selectedReportId) ?? null,
    [reports, selectedReportId],
  )
  const selectedReactionSummary = useMemo(
    () => reactionReports.find((item) => item.report_id === selectedReactionReportId) ?? null,
    [reactionReports, selectedReactionReportId],
  )
  const selectedQuikStrikeSummary = useMemo(
    () => quikStrikeReports.find((item) => item.extraction_id === selectedQuikStrikeId) ?? null,
    [quikStrikeReports, selectedQuikStrikeId],
  )
  const selectedQuikStrikeMatrixSummary = useMemo(
    () =>
      quikStrikeMatrixReports.find((item) => item.extraction_id === selectedQuikStrikeMatrixId) ??
      null,
    [quikStrikeMatrixReports, selectedQuikStrikeMatrixId],
  )
  const selectedFusionSummary = useMemo(
    () => fusionReports.find((item) => item.report_id === selectedFusionReportId) ?? null,
    [fusionReports, selectedFusionReportId],
  )

  const report = dashboardData?.report ?? null
  const warningNotes = uniqueValues([
    ...(report?.warnings ?? []),
    ...(report?.source_validation.warnings ?? []),
  ])
  const limitationNotes = uniqueValues([
    ...(report?.limitations ?? []),
    ...(report?.walls.flatMap((wall) => wall.limitations) ?? []),
    ...(report?.zones.flatMap((zone) => zone.limitations) ?? []),
  ])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-medium uppercase text-amber-300">Research report</p>
          <h2 className="mt-1 text-xl font-semibold">XAU Vol-OI Walls</h2>
          {selectedSummary && (
            <p className="mt-2 text-sm text-gray-400">
              {selectedSummary.report_id} | {selectedSummary.status} |{' '}
              {formatDate(selectedSummary.created_at)}
            </p>
          )}
        </div>
        <label className="flex flex-col gap-2 text-sm text-gray-300">
          Report
          <select
            value={selectedReportId ?? ''}
            onChange={(event) => setSelectedReportId(event.target.value || null)}
            className="min-w-80 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            disabled={loadingReports || reports.length === 0}
          >
            {reports.length === 0 ? (
              <option value="">No XAU reports</option>
            ) : (
              reports.map((item) => (
                <option key={item.report_id} value={item.report_id}>
                  {item.report_id}
                </option>
              ))
            )}
          </select>
        </label>
      </div>

      <ResearchOnlyNotice />
      <QuikStrikeExtractionInspection
        reports={quikStrikeReports}
        selectedExtractionId={selectedQuikStrikeId}
        selectedSummary={selectedQuikStrikeSummary}
        data={quikStrikeData}
        loadingList={loadingQuikStrikeReports}
        loadingReport={loadingQuikStrikeReport}
        error={quikStrikeError}
        onSelect={setSelectedQuikStrikeId}
      />
      <QuikStrikeMatrixInspection
        reports={quikStrikeMatrixReports}
        selectedExtractionId={selectedQuikStrikeMatrixId}
        selectedSummary={selectedQuikStrikeMatrixSummary}
        data={quikStrikeMatrixData}
        loadingList={loadingQuikStrikeMatrixReports}
        loadingReport={loadingQuikStrikeMatrixReport}
        error={quikStrikeMatrixError}
        onSelect={setSelectedQuikStrikeMatrixId}
      />
      <QuikStrikeFusionInspection
        reports={fusionReports}
        selectedReportId={selectedFusionReportId}
        selectedSummary={selectedFusionSummary}
        data={fusionData}
        loadingList={loadingFusionReports}
        loadingReport={loadingFusionReport}
        error={fusionError}
        onSelect={setSelectedFusionReportId}
      />
      <ReactionReportInspection
        reports={reactionReports}
        selectedReportId={selectedReactionReportId}
        selectedSummary={selectedReactionSummary}
        data={reactionData}
        loadingList={loadingReactionReports}
        loadingReport={loadingReactionReport}
        error={reactionError}
        onSelect={setSelectedReactionReportId}
      />

      {error && <Notice tone="error">{error}</Notice>}

      {loadingReports ? (
        <EmptyState>Loading XAU Vol-OI reports...</EmptyState>
      ) : reports.length === 0 ? (
        <EmptyState>No XAU Vol-OI reports are available.</EmptyState>
      ) : loadingReport ? (
        <EmptyState>Loading XAU Vol-OI report...</EmptyState>
      ) : report ? (
        <>
          <StatusSummary report={report} />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <ReportSection title="Basis Snapshot">
              <BasisSnapshot data={report.basis_snapshot} />
            </ReportSection>
            <ReportSection title="Expected Range">
              <ExpectedRangeCard range={report.expected_range} />
            </ReportSection>
          </div>

          {(report.missing_data_instructions.length > 0 ||
            warningNotes.length > 0 ||
            limitationNotes.length > 0) && (
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
              <ReportSection title="Missing Data">
                <NotesList
                  notes={report.missing_data_instructions}
                  emptyText="No missing-data instructions"
                />
              </ReportSection>
              <ReportSection title="Warnings">
                <NotesList notes={warningNotes} emptyText="No warnings" />
              </ReportSection>
              <ReportSection title="Limitations">
                <NotesList notes={limitationNotes} emptyText="No limitations" />
              </ReportSection>
            </div>
          )}

          <ReportSection title="Basis-Adjusted OI Walls">
            <WallTable rows={dashboardData?.walls.data ?? report.walls} />
          </ReportSection>

          <ReportSection title="Zone Classification">
            <ZoneTable rows={dashboardData?.zones.data ?? report.zones} />
          </ReportSection>
        </>
      ) : null}
    </div>
  )
}

function ResearchOnlyNotice() {
  return (
    <Notice tone="warning">
      XAU Vol-OI walls, zones, reactions, and bounded risk plans are research
      annotations only. They require source-data review, context review, and manual
      validation before any operational use.
    </Notice>
  )
}

function QuikStrikeExtractionInspection({
  reports,
  selectedExtractionId,
  selectedSummary,
  data,
  loadingList,
  loadingReport,
  error,
  onSelect,
}: {
  reports: QuikStrikeExtractionSummary[]
  selectedExtractionId: string | null
  selectedSummary: QuikStrikeExtractionSummary | null
  data: QuikStrikeDashboardData | null
  loadingList: boolean
  loadingReport: boolean
  error: string | null
  onSelect: (extractionId: string | null) => void
}) {
  const report = data?.report ?? null
  const conversion = data?.conversion.conversion_result ?? report?.conversion_result ?? null
  const requestedViews = report?.request_summary.requested_views ?? []
  const completedViews = report?.request_summary.completed_views ?? []
  const missingViews = report?.request_summary.missing_views ?? []
  const warnings = uniqueValues([
    ...(report?.warnings ?? []),
    ...(report?.strike_mapping.warnings ?? []),
    ...(conversion?.warnings ?? []),
  ])
  const limitations = uniqueValues([
    ...(report?.limitations ?? []),
    ...(report?.strike_mapping.limitations ?? []),
    ...(conversion?.limitations ?? []),
    ...(report?.research_only_warnings ?? []),
  ])

  return (
    <ReportSection title="QuikStrike Local Extraction">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-gray-400">
            Local sanitized Highcharts extraction reports for Gold Vol2Vol research input.
          </p>
          {selectedSummary && (
            <p className="mt-2 text-sm text-gray-300">
              {selectedSummary.extraction_id} | {selectedSummary.status} |{' '}
              {formatDate(selectedSummary.created_at)}
            </p>
          )}
        </div>
        <label className="flex flex-col gap-2 text-sm text-gray-300">
          QuikStrike extraction
          <select
            value={selectedExtractionId ?? ''}
            onChange={(event) => onSelect(event.target.value || null)}
            className="min-w-80 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            disabled={loadingList || reports.length === 0}
          >
            {reports.length === 0 ? (
              <option value="">No QuikStrike extractions</option>
            ) : (
              reports.map((item) => (
                <option key={item.extraction_id} value={item.extraction_id}>
                  {item.extraction_id}
                </option>
              ))
            )}
          </select>
        </label>
      </div>

      {error && <div className="mt-4"><Notice tone="error">{error}</Notice></div>}

      {loadingList ? (
        <div className="mt-4">
          <EmptyState>Loading QuikStrike extraction reports...</EmptyState>
        </div>
      ) : reports.length === 0 ? (
        <div className="mt-4">
          <EmptyState>No saved QuikStrike extraction reports are available.</EmptyState>
        </div>
      ) : loadingReport ? (
        <div className="mt-4">
          <EmptyState>Loading selected QuikStrike extraction...</EmptyState>
        </div>
      ) : report ? (
        <div className="mt-5 space-y-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <SummaryCard label="Status" value={report.status} />
            <SummaryCard label="Rows" value={report.row_count} />
            <SummaryCard label="Views" value={`${completedViews.length}/${requestedViews.length}`} />
            <SummaryCard label="Strike Map" value={report.strike_mapping.confidence} />
            <SummaryCard label="Conversion" value={conversion?.status ?? 'n/a'} />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <ContextPanel title="View Coverage">
              <dl className="grid grid-cols-1 gap-3 text-sm">
                <Metric label="Requested" value={requestedViews.join(', ') || 'n/a'} />
                <Metric label="Completed" value={completedViews.join(', ') || 'n/a'} />
                <Metric label="Missing" value={missingViews.join(', ') || 'none'} />
              </dl>
            </ContextPanel>
            <ContextPanel title="Strike Mapping">
              <dl className="grid grid-cols-1 gap-3 text-sm">
                <Metric label="Method" value={report.strike_mapping.method} />
                <Metric label="Matched" value={report.strike_mapping.matched_point_count} />
                <Metric label="Unmatched" value={report.strike_mapping.unmatched_point_count} />
                <Metric label="Conflicts" value={report.strike_mapping.conflict_count} />
              </dl>
            </ContextPanel>
            <ContextPanel title="Conversion Rows">
              <dl className="grid grid-cols-1 gap-3 text-sm">
                <Metric label="Status" value={conversion?.status ?? 'n/a'} />
                <Metric label="Rows" value={data?.conversion.rows.length ?? 0} />
                <Metric
                  label="Eligible"
                  value={formatBoolean(Boolean(report.request_summary.conversion_eligible))}
                />
              </dl>
            </ContextPanel>
          </div>

          <ContextPanel title="Output Paths">
            <ArtifactPathList artifacts={report.artifacts} />
          </ContextPanel>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <ContextPanel title="Warnings">
              <NotesList notes={warnings} emptyText="No warnings" />
            </ContextPanel>
            <ContextPanel title="Limitations">
              <NotesList notes={limitations} emptyText="No limitations" />
            </ContextPanel>
            <ContextPanel title="Blocked Conversion Reasons">
              <NotesList
                notes={conversion?.blocked_reasons ?? []}
                emptyText="No conversion blockers"
              />
            </ContextPanel>
          </div>

          <Notice tone="warning">
            QuikStrike extraction is local-only and fixture/report driven here. The
            application does not perform browser RPA, endpoint replay, OCR, or store
            cookies, tokens, headers, HAR files, screenshots, viewstate values, or
            private full URLs.
          </Notice>
        </div>
      ) : null}
    </ReportSection>
  )
}

function QuikStrikeMatrixInspection({
  reports,
  selectedExtractionId,
  selectedSummary,
  data,
  loadingList,
  loadingReport,
  error,
  onSelect,
}: {
  reports: QuikStrikeMatrixExtractionSummary[]
  selectedExtractionId: string | null
  selectedSummary: QuikStrikeMatrixExtractionSummary | null
  data: QuikStrikeMatrixDashboardData | null
  loadingList: boolean
  loadingReport: boolean
  error: string | null
  onSelect: (extractionId: string | null) => void
}) {
  const report = data?.report ?? null
  const conversion = data?.conversion.conversion_result ?? report?.conversion_result ?? null
  const requestedViews = report?.request_summary.requested_views ?? []
  const completedViews = report?.request_summary.completed_views ?? []
  const missingViews = report?.request_summary.missing_views ?? []
  const warnings = uniqueValues([
    ...(report?.warnings ?? []),
    ...(report?.mapping.warnings ?? []),
    ...(conversion?.warnings ?? []),
  ])
  const limitations = uniqueValues([
    ...(report?.limitations ?? []),
    ...(report?.mapping.limitations ?? []),
    ...(conversion?.limitations ?? []),
    ...(report?.research_only_warnings ?? []),
  ])

  return (
    <ReportSection title="QuikStrike OI Matrix Extraction">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-gray-400">
            Local sanitized Open Interest Matrix table extraction reports for Gold OI,
            OI change, and volume research input.
          </p>
          {selectedSummary && (
            <p className="mt-2 text-sm text-gray-300">
              {selectedSummary.extraction_id} | {selectedSummary.status} |{' '}
              {formatDate(selectedSummary.created_at)}
            </p>
          )}
        </div>
        <label className="flex flex-col gap-2 text-sm text-gray-300">
          Matrix extraction
          <select
            value={selectedExtractionId ?? ''}
            onChange={(event) => onSelect(event.target.value || null)}
            className="min-w-80 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            disabled={loadingList || reports.length === 0}
          >
            {reports.length === 0 ? (
              <option value="">No Matrix extractions</option>
            ) : (
              reports.map((item) => (
                <option key={item.extraction_id} value={item.extraction_id}>
                  {item.extraction_id}
                </option>
              ))
            )}
          </select>
        </label>
      </div>

      {error && <div className="mt-4"><Notice tone="error">{error}</Notice></div>}

      {loadingList ? (
        <div className="mt-4">
          <EmptyState>Loading QuikStrike Matrix reports...</EmptyState>
        </div>
      ) : reports.length === 0 ? (
        <div className="mt-4">
          <EmptyState>No saved QuikStrike Matrix extraction reports are available.</EmptyState>
        </div>
      ) : loadingReport ? (
        <div className="mt-4">
          <EmptyState>Loading selected QuikStrike Matrix extraction...</EmptyState>
        </div>
      ) : report ? (
        <div className="mt-5 space-y-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            <SummaryCard label="Status" value={report.status} />
            <SummaryCard label="Rows" value={report.row_count} />
            <SummaryCard label="Strikes" value={report.strike_count} />
            <SummaryCard label="Expiries" value={report.expiration_count} />
            <SummaryCard label="Unavailable" value={report.unavailable_cell_count} />
            <SummaryCard label="Conversion" value={conversion?.status ?? 'n/a'} />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <ContextPanel title="View Coverage">
              <dl className="grid grid-cols-1 gap-3 text-sm">
                <Metric label="Requested" value={requestedViews.join(', ') || 'n/a'} />
                <Metric label="Completed" value={completedViews.join(', ') || 'n/a'} />
                <Metric label="Missing" value={missingViews.join(', ') || 'none'} />
              </dl>
            </ContextPanel>
            <ContextPanel title="Mapping Validation">
              <dl className="grid grid-cols-1 gap-3 text-sm">
                <Metric label="Status" value={report.mapping.status} />
                <Metric label="Option Sides" value={report.mapping.option_side_mapping} />
                <Metric label="Numeric Cells" value={report.mapping.numeric_cell_count} />
                <Metric label="Duplicates" value={report.mapping.duplicate_row_count} />
              </dl>
            </ContextPanel>
            <ContextPanel title="Conversion Rows">
              <dl className="grid grid-cols-1 gap-3 text-sm">
                <Metric label="Status" value={conversion?.status ?? 'n/a'} />
                <Metric label="Rows" value={data?.conversion.rows.length ?? 0} />
                <Metric
                  label="Eligible"
                  value={formatBoolean(Boolean(report.request_summary.conversion_eligible))}
                />
              </dl>
            </ContextPanel>
          </div>

          <ContextPanel title="Output Paths">
            <ArtifactPathList artifacts={report.artifacts} />
          </ContextPanel>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <ContextPanel title="Warnings">
              <NotesList notes={warnings} emptyText="No warnings" />
            </ContextPanel>
            <ContextPanel title="Limitations">
              <NotesList notes={limitations} emptyText="No limitations" />
            </ContextPanel>
            <ContextPanel title="Blocked Conversion Reasons">
              <NotesList
                notes={[...report.mapping.blocked_reasons, ...(conversion?.blocked_reasons ?? [])]}
                emptyText="No conversion blockers"
              />
            </ContextPanel>
          </div>

          <Notice tone="warning">
            QuikStrike Matrix extraction is local-only and fixture/report driven here.
            The application does not perform endpoint replay, OCR, credential storage,
            or store cookies, tokens, headers, HAR files, screenshots, viewstate values,
            or private full URLs.
          </Notice>
        </div>
      ) : null}
    </ReportSection>
  )
}

function QuikStrikeFusionInspection({
  reports,
  selectedReportId,
  selectedSummary,
  data,
  loadingList,
  loadingReport,
  error,
  onSelect,
}: {
  reports: XauQuikStrikeFusionSummary[]
  selectedReportId: string | null
  selectedSummary: XauQuikStrikeFusionSummary | null
  data: XauQuikStrikeFusionDashboardData | null
  loadingList: boolean
  loadingReport: boolean
  error: string | null
  onSelect: (reportId: string | null) => void
}) {
  const report = data?.report ?? null
  const rowCount = data?.rows.rows.length ?? selectedSummary?.fused_row_count ?? 0
  const missingContext = data?.missingContext.missing_context ?? []
  const artifacts = report?.artifacts ?? []
  const downstream = report?.downstream_result ?? null

  return (
    <ReportSection title="QuikStrike Fusion Context">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-gray-400">
            Local-only fusion context for saved Vol2Vol and Matrix reports.
          </p>
          {selectedSummary && (
            <p className="mt-2 text-sm text-gray-300">
              {selectedSummary.report_id} | {selectedSummary.status} |{' '}
              {formatDate(selectedSummary.created_at)}
            </p>
          )}
        </div>
        <label className="flex flex-col gap-2 text-sm text-gray-300">
          Fusion report
          <select
            value={selectedReportId ?? ''}
            onChange={(event) => onSelect(event.target.value || null)}
            className="min-w-80 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            disabled={loadingList || reports.length === 0}
          >
            {reports.length === 0 ? (
              <option value="">No fusion reports</option>
            ) : (
              reports.map((item) => (
                <option key={item.report_id} value={item.report_id}>
                  {item.report_id}
                </option>
              ))
            )}
          </select>
        </label>
      </div>

      {error && <div className="mt-4"><Notice tone="error">{error}</Notice></div>}

      {loadingList ? (
        <div className="mt-4">
          <EmptyState>Loading QuikStrike fusion reports...</EmptyState>
        </div>
      ) : reports.length === 0 ? (
        <div className="mt-4 space-y-4">
          <EmptyState>No saved QuikStrike fusion reports are available.</EmptyState>
          <ContextPanel title="Foundation Status">
            <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
              <Metric label="Route" value="registered" />
              <Metric label="Source loading" value="pending" />
              <Metric label="Matching" value="pending" />
              <Metric label="Downstream reports" value="pending" />
            </dl>
            <p className="mt-3 text-sm text-gray-400">
              Fusion remains a local research inspection surface. This placeholder does not
              trigger browser extraction or downstream XAU report creation.
            </p>
          </ContextPanel>
        </div>
      ) : selectedSummary ? (
        <div className="mt-5 space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <SummaryCard label="Status" value={selectedSummary.status} />
            <SummaryCard label="Fused Rows" value={rowCount} />
            <SummaryCard label="Strikes" value={selectedSummary.strike_count} />
            <SummaryCard label="Expiries" value={selectedSummary.expiration_count} />
            <SummaryCard label="Warnings" value={selectedSummary.warning_count} />
          </div>
          {loadingReport && <EmptyState>Loading fusion report detail...</EmptyState>}
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <ContextPanel title="Source Reports">
              <dl className="grid grid-cols-1 gap-3 text-sm">
                <Metric
                  label="Vol2Vol"
                  value={report?.vol2vol_source.report_id ?? selectedSummary.vol2vol_report_id}
                />
                <Metric
                  label="Vol2Vol Rows"
                  value={report?.vol2vol_source.row_count ?? 'n/a'}
                />
                <Metric
                  label="Matrix"
                  value={report?.matrix_source.report_id ?? selectedSummary.matrix_report_id}
                />
                <Metric label="Matrix Rows" value={report?.matrix_source.row_count ?? 'n/a'} />
              </dl>
            </ContextPanel>
            <ContextPanel title="Context Status">
              <dl className="grid grid-cols-1 gap-3 text-sm">
                <Metric label="Basis" value={selectedSummary.basis_status} />
                <Metric label="IV / Range" value={selectedSummary.iv_range_status} />
                <Metric label="Open" value={selectedSummary.open_regime_status} />
                <Metric label="Candle" value={selectedSummary.candle_acceptance_status} />
                <Metric
                  label="Realized Vol"
                  value={report?.context_summary?.realized_volatility_status ?? 'n/a'}
                />
                <Metric
                  label="Source Agreement"
                  value={report?.context_summary?.source_agreement_status ?? 'n/a'}
                />
              </dl>
            </ContextPanel>
            <ContextPanel title="Linked XAU Reports">
              <dl className="grid grid-cols-1 gap-3 text-sm">
                <Metric
                  label="Vol-OI"
                  value={
                    downstream?.xau_vol_oi_report_id ??
                    selectedSummary.xau_vol_oi_report_id ??
                    'n/a'
                  }
                />
                <Metric
                  label="Reaction"
                  value={
                    downstream?.xau_reaction_report_id ??
                    selectedSummary.xau_reaction_report_id ??
                    'n/a'
                  }
                />
                <Metric label="Reaction Rows" value={downstream?.reaction_row_count ?? 'n/a'} />
                <Metric label="No-Trade Rows" value={downstream?.no_trade_count ?? 'n/a'} />
                <Metric
                  label="All No-Trade"
                  value={
                    (downstream?.all_reactions_no_trade ??
                      selectedSummary.all_reactions_no_trade) === null
                      ? 'n/a'
                      : formatBoolean(
                          downstream?.all_reactions_no_trade ??
                            selectedSummary.all_reactions_no_trade ??
                            false,
                        )
                  }
                />
              </dl>
            </ContextPanel>
          </div>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <ContextPanel title="Coverage">
              <dl className="grid grid-cols-1 gap-3 text-sm">
                <Metric label="Matched Keys" value={report?.coverage?.matched_key_count ?? 'n/a'} />
                <Metric
                  label="Vol2Vol Only"
                  value={report?.coverage?.vol2vol_only_key_count ?? 'n/a'}
                />
                <Metric
                  label="Matrix Only"
                  value={report?.coverage?.matrix_only_key_count ?? 'n/a'}
                />
                <Metric
                  label="Conflicts"
                  value={report?.coverage?.conflict_key_count ?? 'n/a'}
                />
              </dl>
            </ContextPanel>
            <ContextPanel title="Missing Context">
              <NotesList
                notes={missingContext.map(
                  (item) => `${item.context_key}: ${item.status} - ${item.message}`,
                )}
                emptyText="No missing-context items"
              />
            </ContextPanel>
            <ContextPanel title="Artifacts">
              <NotesList
                notes={artifacts.map((artifact) => `${artifact.artifact_type}: ${artifact.path}`)}
                emptyText="No artifacts recorded"
              />
            </ContextPanel>
          </div>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <ContextPanel title="Warnings">
              <NotesList notes={report?.warnings ?? []} emptyText="No fusion warnings" />
            </ContextPanel>
            <ContextPanel title="Limitations">
              <NotesList
                notes={[
                  ...(report?.limitations ?? []),
                  ...(report?.research_only_warnings ?? []),
                ]}
                emptyText="No limitations recorded"
              />
            </ContextPanel>
          </div>
          <Notice tone="warning">
            Fusion is local-only and research-only. It does not trigger browser extraction,
            endpoint replay, credential handling, order execution, or live-readiness claims.
          </Notice>
        </div>
      ) : null}
    </ReportSection>
  )
}

function ReactionReportInspection({
  reports,
  selectedReportId,
  selectedSummary,
  data,
  loadingList,
  loadingReport,
  error,
  onSelect,
}: {
  reports: XauReactionReportSummary[]
  selectedReportId: string | null
  selectedSummary: XauReactionReportSummary | null
  data: XauReactionDashboardData | null
  loadingList: boolean
  loadingReport: boolean
  error: string | null
  onSelect: (reportId: string | null) => void
}) {
  const report = data?.report ?? null
  const reactions = data?.reactions.data ?? report?.reactions ?? []
  const riskPlans = data?.riskPlan.data ?? report?.risk_plans ?? []
  const acceptanceStates = reactions
    .map((reaction) => reaction.acceptance_state)
    .filter((state): state is XauAcceptanceResult => state !== null)
  const noTradeReasons = uniqueValues(reactions.flatMap((reaction) => reaction.no_trade_reasons))

  return (
    <ReportSection title="XAU Reaction Reports">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-gray-400">
            Saved reaction reports derived from feature 006 XAU Vol-OI reports.
          </p>
          {selectedSummary && (
            <p className="mt-2 text-sm text-gray-300">
              Source report: {selectedSummary.source_report_id} | {selectedSummary.status} |{' '}
              {formatDate(selectedSummary.created_at)}
            </p>
          )}
        </div>
        <label className="flex flex-col gap-2 text-sm text-gray-300">
          Reaction report
          <select
            value={selectedReportId ?? ''}
            onChange={(event) => onSelect(event.target.value || null)}
            className="min-w-80 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            disabled={loadingList || reports.length === 0}
          >
            {reports.length === 0 ? (
              <option value="">No reaction reports</option>
            ) : (
              reports.map((item) => (
                <option key={item.report_id} value={item.report_id}>
                  {item.report_id}
                </option>
              ))
            )}
          </select>
        </label>
      </div>

      {error && <div className="mt-4"><Notice tone="error">{error}</Notice></div>}

      {loadingList ? (
        <div className="mt-4">
          <EmptyState>Loading XAU reaction reports...</EmptyState>
        </div>
      ) : reports.length === 0 ? (
        <div className="mt-4">
          <EmptyState>No saved XAU reaction reports are available.</EmptyState>
        </div>
      ) : loadingReport ? (
        <div className="mt-4">
          <EmptyState>Loading selected XAU reaction report...</EmptyState>
        </div>
      ) : report ? (
        <div className="mt-5 space-y-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <SummaryCard label="Status" value={report.status} />
            <SummaryCard label="Source Walls" value={report.source_wall_count} />
            <SummaryCard label="Reactions" value={report.reaction_count} />
            <SummaryCard label="No-Trade" value={report.no_trade_count} />
            <SummaryCard label="Risk Plans" value={report.risk_plan_count} />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <ContextPanel title="Freshness">
              <FreshnessPanel state={report.freshness_state} />
            </ContextPanel>
            <ContextPanel title="IV/RV/VRP">
              <VolRegimePanel state={report.vol_regime_state} />
            </ContextPanel>
            <ContextPanel title="Session Open">
              <OpenRegimePanel state={report.open_regime_state} />
            </ContextPanel>
          </div>

          <ContextPanel title="Acceptance / Rejection State">
            <AcceptanceStateList states={acceptanceStates} />
          </ContextPanel>

          <ContextPanel title="Reaction Labels">
            <ReactionTable rows={reactions} />
          </ContextPanel>

          <ContextPanel title="Bounded Risk Planner">
            <RiskPlanTable rows={riskPlans} />
          </ContextPanel>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <ContextPanel title="No-Trade Reasons">
              <NotesList notes={noTradeReasons} emptyText="No no-trade reasons in this report" />
            </ContextPanel>
            <ContextPanel title="Warnings">
              <NotesList notes={report.warnings} emptyText="No warnings" />
            </ContextPanel>
            <ContextPanel title="Limitations">
              <NotesList notes={report.limitations} emptyText="No limitations" />
            </ContextPanel>
          </div>
        </div>
      ) : null}
    </ReportSection>
  )
}

function StatusSummary({ report }: { report: NonNullable<XauDashboardData['report']> }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <SummaryCard label="Status" value={report.status} />
      <SummaryCard label="Source Rows" value={report.source_row_count} />
      <SummaryCard label="Accepted" value={report.accepted_row_count} />
      <SummaryCard label="Walls" value={report.wall_count} />
      <SummaryCard label="Zones" value={report.zone_count} />
    </div>
  )
}

function ContextPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-gray-700 bg-gray-900 p-4">
      <h4 className="mb-3 text-sm font-semibold text-gray-100">{title}</h4>
      {children}
    </div>
  )
}

function FreshnessPanel({ state }: { state: XauFreshnessResult }) {
  return (
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
      <Metric label="State" value={state.state} />
      <Metric label="Confidence" value={state.confidence_label} />
      <Metric label="Age Minutes" value={formatNumber(state.age_minutes)} />
      <Metric label="No-Trade Reason" value={state.no_trade_reason ?? 'n/a'} />
      {state.notes.length > 0 && (
        <div className="sm:col-span-2">
          <NotesList notes={state.notes} emptyText="No freshness notes" />
        </div>
      )}
    </dl>
  )
}

function VolRegimePanel({ state }: { state: XauVolRegimeResult }) {
  return (
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
      <Metric label="Realized Vol" value={formatNumber(state.realized_volatility)} />
      <Metric label="VRP" value={formatNumber(state.vrp)} />
      <Metric label="VRP Regime" value={state.vrp_regime} />
      <Metric label="IV Edge" value={state.iv_edge_state} />
      <Metric label="RV Extension" value={state.rv_extension_state} />
      <Metric label="Confidence" value={state.confidence_label} />
      {state.notes.length > 0 && (
        <div className="sm:col-span-2">
          <NotesList notes={state.notes} emptyText="No volatility notes" />
        </div>
      )}
    </dl>
  )
}

function OpenRegimePanel({ state }: { state: XauOpenRegimeResult }) {
  return (
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
      <Metric label="Open Side" value={state.open_side} />
      <Metric label="Distance" value={formatNumber(state.open_distance_points)} />
      <Metric label="Flip State" value={state.open_flip_state} />
      <Metric label="Boundary" value={state.open_as_support_or_resistance} />
      <Metric label="Confidence" value={state.confidence_label} />
      {state.notes.length > 0 && (
        <div className="sm:col-span-2">
          <NotesList notes={state.notes} emptyText="No open-regime notes" />
        </div>
      )}
    </dl>
  )
}

function AcceptanceStateList({ states }: { states: XauAcceptanceResult[] }) {
  if (states.length === 0) {
    return <p className="text-sm text-gray-400">No candle acceptance state was recorded.</p>
  }
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {states.map((state) => (
        <div key={`${state.wall_id ?? 'wall'}-${state.zone_id ?? 'zone'}`} className="text-sm">
          <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Metric label="Wall" value={state.wall_id ?? 'n/a'} />
            <Metric label="Zone" value={state.zone_id ?? 'n/a'} />
            <Metric label="Direction" value={state.direction} />
            <Metric label="Confidence" value={state.confidence_label} />
            <Metric label="Accepted" value={formatBoolean(state.accepted_beyond_wall)} />
            <Metric label="Confirmed" value={formatBoolean(state.confirmed_breakout)} />
            <Metric label="Wick Rejection" value={formatBoolean(state.wick_rejection)} />
            <Metric label="Failed Break" value={formatBoolean(state.failed_breakout)} />
          </dl>
          {state.notes.length > 0 && (
            <div className="mt-3">
              <NotesList notes={state.notes} emptyText="No acceptance notes" />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function SummaryCard({ label, value }: { label: number | string; value: number | string }) {
  return (
    <div className="rounded-md bg-gray-800 p-4">
      <div className="text-xs uppercase text-gray-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
    </div>
  )
}

function ReportSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-md bg-gray-800 p-4">
      <h3 className="mb-4 text-base font-semibold">{title}</h3>
      {children}
    </section>
  )
}

function Notice({ tone, children }: { tone: 'warning' | 'error'; children: ReactNode }) {
  const toneClass =
    tone === 'error'
      ? 'border-red-900 bg-red-950 text-red-200'
      : 'border-amber-900 bg-amber-950 text-amber-100'
  return <div className={`rounded-md border px-4 py-3 text-sm ${toneClass}`}>{children}</div>
}

function EmptyState({ children }: { children: ReactNode }) {
  return <div className="rounded-md bg-gray-800 p-4 text-sm text-gray-400">{children}</div>
}

function BasisSnapshot({ data }: { data: XauDashboardData['report']['basis_snapshot'] }) {
  if (!data) {
    return <p className="text-sm text-gray-400">Basis snapshot unavailable.</p>
  }
  return (
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
      <Metric label="Basis" value={formatNumber(data.basis)} />
      <Metric label="Source" value={data.basis_source} />
      <Metric label="Mapping" value={data.mapping_available ? 'available' : 'unavailable'} />
      <Metric label="Alignment" value={data.timestamp_alignment_status} />
      <Metric label="Spot" value={data.spot_reference?.symbol ?? 'n/a'} />
      <Metric label="Futures" value={data.futures_reference?.symbol ?? 'n/a'} />
      {data.notes.length > 0 && (
        <div className="sm:col-span-2">
          <NotesList notes={data.notes} emptyText="No basis notes" />
        </div>
      )}
    </dl>
  )
}

function ExpectedRangeCard({ range }: { range: XauExpectedRange | null }) {
  if (!range) {
    return <p className="text-sm text-gray-400">Expected range unavailable.</p>
  }
  return (
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
      <Metric label="Source" value={range.source} />
      <Metric label="Reference" value={formatNumber(range.reference_price)} />
      <Metric label="Expected Move" value={formatNumber(range.expected_move)} />
      <Metric label="Days" value={range.days_to_expiry ?? 'n/a'} />
      <Metric label="Lower 1SD" value={formatNumber(range.lower_1sd)} />
      <Metric label="Upper 1SD" value={formatNumber(range.upper_1sd)} />
      <Metric label="Lower 2SD" value={formatNumber(range.lower_2sd)} />
      <Metric label="Upper 2SD" value={formatNumber(range.upper_2sd)} />
      {range.unavailable_reason && (
        <div className="sm:col-span-2 text-amber-200">{range.unavailable_reason}</div>
      )}
    </dl>
  )
}

function ArtifactPathList({
  artifacts,
}: {
  artifacts: Array<{ artifact_type: string; path: string; rows: number | null }>
}) {
  if (artifacts.length === 0) {
    return <p className="text-sm text-gray-400">No local artifact paths were recorded.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Artifact</th>
            <th className="px-3 py-2">Rows</th>
            <th className="px-3 py-2">Path</th>
          </tr>
        </thead>
        <tbody>
          {artifacts.map((artifact) => (
            <tr
              key={`${artifact.artifact_type}-${artifact.path}`}
              className="border-t border-gray-700"
            >
              <td className="px-3 py-2">{artifact.artifact_type}</td>
              <td className="px-3 py-2">{artifact.rows ?? 'n/a'}</td>
              <td className="max-w-xl break-all px-3 py-2 text-gray-300">{artifact.path}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <dt className="text-xs uppercase text-gray-400">{label}</dt>
      <dd className="mt-1 text-white">{value}</dd>
    </div>
  )
}

function WallTable({ rows }: { rows: XauOiWall[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-400">No wall rows were generated.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Expiry</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2">Strike</th>
            <th className="px-3 py-2">Spot Eq.</th>
            <th className="px-3 py-2">OI</th>
            <th className="px-3 py-2">OI Share</th>
            <th className="px-3 py-2">Expiry Weight</th>
            <th className="px-3 py-2">Freshness</th>
            <th className="px-3 py-2">Score</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.wall_id} className="border-t border-gray-700">
              <td className="px-3 py-2">{row.expiry}</td>
              <td className="px-3 py-2">{row.option_type}</td>
              <td className="px-3 py-2">{formatNumber(row.strike)}</td>
              <td className="px-3 py-2">{formatNumber(row.spot_equivalent_level)}</td>
              <td className="px-3 py-2">{formatNumber(row.open_interest)}</td>
              <td className="px-3 py-2">{formatPercent(row.oi_share)}</td>
              <td className="px-3 py-2">{formatNumber(row.expiry_weight)}</td>
              <td className="px-3 py-2">{row.freshness_status}</td>
              <td className="px-3 py-2">{formatNumber(row.wall_score)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ZoneTable({ rows }: { rows: XauZone[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-400">No zone rows were generated.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Zone</th>
            <th className="px-3 py-2">Level</th>
            <th className="px-3 py-2">Bounds</th>
            <th className="px-3 py-2">Wall Score</th>
            <th className="px-3 py-2">Pin</th>
            <th className="px-3 py-2">Squeeze</th>
            <th className="px-3 py-2">Confidence</th>
            <th className="px-3 py-2">No-trade</th>
            <th className="px-3 py-2">Notes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.zone_id} className="border-t border-gray-700 align-top">
              <td className="px-3 py-2">{row.zone_type}</td>
              <td className="px-3 py-2">{formatNumber(row.level)}</td>
              <td className="px-3 py-2">
                {formatNumber(row.lower_bound)} / {formatNumber(row.upper_bound)}
              </td>
              <td className="px-3 py-2">{formatNumber(row.wall_score)}</td>
              <td className="px-3 py-2">{formatNumber(row.pin_risk_score)}</td>
              <td className="px-3 py-2">{formatNumber(row.squeeze_risk_score)}</td>
              <td className="px-3 py-2">{row.confidence}</td>
              <td className="px-3 py-2">{row.no_trade_warning ? 'yes' : 'no'}</td>
              <td className="max-w-md px-3 py-2 text-gray-300">{row.notes.join(' ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ReactionTable({ rows }: { rows: XauReactionRow[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-400">No reaction rows were generated.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Reaction</th>
            <th className="px-3 py-2">Wall</th>
            <th className="px-3 py-2">Zone</th>
            <th className="px-3 py-2">Label</th>
            <th className="px-3 py-2">Confidence</th>
            <th className="px-3 py-2">Invalidation</th>
            <th className="px-3 py-2">Target 1</th>
            <th className="px-3 py-2">Target 2</th>
            <th className="px-3 py-2">Next Wall</th>
            <th className="px-3 py-2">Notes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.reaction_id} className="border-t border-gray-700 align-top">
              <td className="px-3 py-2">{row.reaction_id}</td>
              <td className="px-3 py-2">{row.wall_id ?? 'n/a'}</td>
              <td className="px-3 py-2">{row.zone_id ?? 'n/a'}</td>
              <td className="px-3 py-2">{row.reaction_label}</td>
              <td className="px-3 py-2">{row.confidence_label}</td>
              <td className="px-3 py-2">{formatNumber(row.invalidation_level)}</td>
              <td className="px-3 py-2">{formatNumber(row.target_level_1)}</td>
              <td className="px-3 py-2">{formatNumber(row.target_level_2)}</td>
              <td className="px-3 py-2">{row.next_wall_reference ?? 'n/a'}</td>
              <td className="max-w-md px-3 py-2 text-gray-300">
                {row.explanation_notes.join(' ')}
                {row.no_trade_reasons.length > 0 && (
                  <div className="mt-2 text-amber-200">
                    {row.no_trade_reasons.join(' ')}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RiskPlanTable({ rows }: { rows: XauRiskPlan[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-400">No bounded risk-plan rows were generated.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Plan</th>
            <th className="px-3 py-2">Reaction</th>
            <th className="px-3 py-2">Label</th>
            <th className="px-3 py-2">Condition</th>
            <th className="px-3 py-2">Invalidation</th>
            <th className="px-3 py-2">Buffer</th>
            <th className="px-3 py-2">Target 1</th>
            <th className="px-3 py-2">Target 2</th>
            <th className="px-3 py-2">Recovery</th>
            <th className="px-3 py-2">RR State</th>
            <th className="px-3 py-2">Cancel Conditions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.plan_id} className="border-t border-gray-700 align-top">
              <td className="px-3 py-2">{row.plan_id}</td>
              <td className="px-3 py-2">{row.reaction_id}</td>
              <td className="px-3 py-2">{row.reaction_label}</td>
              <td className="max-w-sm px-3 py-2 text-gray-300">
                {row.entry_condition_text ?? 'n/a'}
              </td>
              <td className="px-3 py-2">{formatNumber(row.invalidation_level)}</td>
              <td className="px-3 py-2">{formatNumber(row.stop_buffer_points)}</td>
              <td className="px-3 py-2">{formatNumber(row.target_1)}</td>
              <td className="px-3 py-2">{formatNumber(row.target_2)}</td>
              <td className="px-3 py-2">{row.max_recovery_legs}</td>
              <td className="px-3 py-2">{row.rr_state}</td>
              <td className="max-w-md px-3 py-2 text-gray-300">
                {[...row.cancel_conditions, ...row.risk_notes].join(' ')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function NotesList({ notes, emptyText }: { notes: string[]; emptyText: string }) {
  if (notes.length === 0) {
    return <p className="text-sm text-gray-400">{emptyText}</p>
  }
  return (
    <ul className="space-y-2 text-sm text-gray-300">
      {notes.map((note) => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  )
}

function uniqueValues(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)))
}

function formatDate(value: string | null): string {
  if (!value) return 'n/a'
  return new Date(value).toLocaleString()
}

function formatNumber(value: number | null): string {
  if (value === null || Number.isNaN(value)) return 'n/a'
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function formatBoolean(value: boolean): string {
  return value ? 'yes' : 'no'
}

function formatPercent(value: number): string {
  return `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}%`
}
