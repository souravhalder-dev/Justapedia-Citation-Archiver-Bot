export interface SystemStatus {
  status: string;
  wiki_connected: boolean;
  wiki_api_url: string;
  developer: {
    name: string;
    email: string;
  };
  db_stats: {
    cached_urls: number;
    cached_snapshots: number;
    total_jobs: number;
    articles_processed: number;
  };
}

export interface UserSession {
  token: string;
  username: string;
  user_id: number | null;
}

export interface AutoModeStatus {
  state: "stopped" | "running" | "paused";
  running_user: string | null;
  target_category: string;
  dry_run: boolean;
  articles_scanned: number;
  articles_updated: number;
  citations_updated: number;
  current_article: string;
  speed_articles_per_minute: number;
  elapsed_seconds: number;
  recent_activities: Array<{
    timestamp: string;
    message: string;
    level: "info" | "success" | "warning" | "error";
  }>;
}

export interface ArticleVersion {
  id: number;
  article_title: string;
  version_num: number;
  username: string;
  mode: string;
  previous_wikitext: string;
  updated_wikitext: string;
  diff: string;
  citations_updated: number;
  mediawiki_revid: number | null;
  summary: string;
  created_at: string;
}

export interface BotMetrics {
  articles_scanned: number;
  citations_examined: number;
  urls_checked: number;
  working_urls: number;
  potentially_dead_urls: number;
  inconclusive_urls: number;
  archives_found: number;
  archive_params_added: number;
  existing_archives_preserved: number;
  citations_skipped: number;
  api_failures: number;
  edit_failures: number;
  articles_updated: number;
}

export interface CitationItem {
  article_title: string;
  citation_title: string | null;
  original_url: string | null;
  url_health: "working" | "likely_dead" | "inconclusive" | "unknown";
  archive_url: string | null;
  archive_date: string | null;
  action_taken: string;
  reason: string;
}

export interface ScanReport {
  job_id: string;
  target_type: string;
  target: string;
  mode: "dry_run" | "live_edit";
  started_at: string;
  finished_at: string | null;
  metrics: BotMetrics;
  citations_count: number;
  citations: CitationItem[];
  articles_with_diffs: string[];
}

export interface ScanResponse {
  job_id: string;
  report: ScanReport;
  diffs: Record<string, string>;
  error?: string;
}

export interface UrlCheckResult {
  url: string;
  health: {
    status: "working" | "likely_dead" | "inconclusive" | "unknown";
    http_code: number | null;
    final_url: string | null;
    is_cached: boolean;
    error_message: string | null;
  };
  snapshot: {
    archive_url: string;
    timestamp: string;
    formatted_date: string;
    status_code: number;
    source_api: string;
    is_cached: boolean;
  } | null;
  recent_cdx_captures: Array<{
    timestamp: string;
    archive_url: string;
    status_code: number;
    mime_type: string;
    date: string;
  }>;
}

export interface JobRecord {
  id: string;
  target_type: string;
  target: string;
  mode: string;
  status: string;
  articles_scanned: number;
  citations_examined: number;
  urls_checked: number;
  archives_added: number;
  edits_made: number;
  errors_count: number;
  created_at: string;
  updated_at: string;
}
