import { Component, DestroyRef, inject, provideZonelessChangeDetection, signal } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { HttpClient, HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { Subscription, timeout } from 'rxjs';
import { Analysis, FindingsPage, Status, UUID, canonicalRepository, decodeAnalysis, decodeFindings, decodeSubmission, publicErrorCode } from './api';

const STATUS: Record<Status, string> = { queued: 'Na fila', running: 'Em análise', completed: 'Concluída', failed: 'Falhou' };
const CATEGORY: Record<string, string> = { architecture: 'Arquitetura', maintainability: 'Manutenção', reliability: 'Confiabilidade', security: 'Segurança', testing: 'Testes' };
const SEVERITY: Record<string, string> = { info: 'Informativa', low: 'Baixa', medium: 'Média', high: 'Alta', critical: 'Crítica' };
const OMISSION: Record<string, string> = { binary: 'Binários', generated: 'Gerados', vendor: 'Dependências', sensitive: 'Sensíveis', unsupported_text: 'Texto não elegível', context_budget: 'Limite de contexto', submodule: 'Submódulos', lfs: 'Git LFS' };
const ERRORS: Record<string, string> = {
  validation_failed: 'Informe uma URL pública no formato https://github.com/autor/repositorio.',
  access_denied: 'Acesso permitido apenas pela origem local configurada. Abra a aplicação pelo endereço local do Nginx.',
  analysis_not_found: 'Análise não encontrada. Confira o identificador ou inicie uma nova análise.',
  idempotency_conflict: 'Este envio está vinculado a outra URL. Inicie uma nova análise.',
  analysis_not_completed: 'Os resultados ainda não estão disponíveis. Atualize o estado da análise.',
  admission_limited: 'O limite de envios ou da fila foi atingido. Aguarde antes de tentar novamente.',
  application_unavailable: 'A aplicação está temporariamente indisponível. Tente novamente mais tarde.',
  configuration_error: 'A análise não foi executada porque o provedor de IA não está configurado. Confira as configurações locais do serviço de IA.',
  repository_unavailable: 'O repositório não está disponível publicamente. Confira a URL e a visibilidade no GitHub.',
  unsafe_snapshot: 'O conteúdo do repositório não pôde ser inspecionado com segurança. Nenhum resultado foi publicado.',
  limit_exceeded: 'O repositório ou a resposta excedeu os limites da análise. Tente um repositório menor.',
  no_eligible_context: 'Não foram encontrados arquivos de texto elegíveis para análise.',
  invalid_findings: 'A resposta da IA não passou na validação. Nenhum achado foi publicado.',
  invalid_result: 'A resposta não passou na validação. Nenhum resultado parcial foi publicado.',
  network_unavailable: 'Não foi possível acessar um serviço externo.',
  upstream_timeout: 'Um serviço externo excedeu o tempo disponível.',
  upstream_rate_limited: 'Um serviço externo limitou as requisições.',
  upstream_unavailable: 'Um serviço externo está temporariamente indisponível.',
  attempt_expired: 'A tentativa expirou antes de confirmar o resultado.',
  queue_unavailable: 'A fila está temporariamente indisponível.',
};

@Component({ selector: 'app-root', standalone: true, templateUrl: './app.html' })
export class AppComponent {
  readonly url = signal(''); readonly acknowledged = signal(false);
  readonly submitting = signal(false); readonly submissionError = signal('');
  readonly analysis = signal<Analysis | null>(null); readonly analysisId = signal('');
  readonly statusLoading = signal(false); readonly statusError = signal(''); readonly paused = signal(false);
  readonly page = signal<FindingsPage | null>(null); readonly resultsLoading = signal(false); readonly resultsError = signal('');
  readonly retryUntil = signal(0); readonly secondsLeft = signal(0);
  readonly requestedPage = signal(1);
  readonly perPage = 5;
  readonly statusLabel = STATUS; readonly categoryLabel = CATEGORY; readonly severityLabel = SEVERITY; readonly omissionLabel = OMISSION;
  private readonly http = inject(HttpClient);
  private readonly destroy = inject(DestroyRef);
  private submitRequest?: Subscription; private statusRequest?: Subscription; private resultsRequest?: Subscription;
  private pollTimer?: ReturnType<typeof setTimeout>; private cooldown?: ReturnType<typeof setInterval>;
  private pollDelay = 2000; private failures = 0; private viewVersion = 0;
  private pending: { url: string; key: string } | null = null;

  constructor() {
    try {
      const saved = JSON.parse(sessionStorage.getItem('analysis-submission-v1') ?? 'null');
      if (saved && canonicalRepository(saved.url) === saved.url && UUID.test(saved.key)) {
        this.pending = saved; this.url.set(saved.url);
      }
    } catch { /* Storage is optional; never block a local client. */ }
    const navigate = () => this.openHash();
    window.addEventListener('hashchange', navigate);
    this.destroy.onDestroy(() => {
      this.stopViewing(); this.submitRequest?.unsubscribe(); clearInterval(this.cooldown);
      window.removeEventListener('hashchange', navigate);
    });
    this.openHash();
  }

  canSubmit(): boolean { return !this.submitting() && this.acknowledged() && !!canonicalRepository(this.url()) && this.secondsLeft() === 0; }
  setUrl(event: Event): void { this.url.set((event.target as HTMLInputElement).value); this.submissionError.set(''); }
  submit(event: Event): void {
    event.preventDefault(); if (!this.canSubmit()) return;
    const url = canonicalRepository(this.url())!;
    if (!this.pending || this.pending.url !== url) this.pending = { url, key: crypto.randomUUID() };
    try { sessionStorage.setItem('analysis-submission-v1', JSON.stringify(this.pending)); } catch { /* Optional storage. */ }
    this.submitting.set(true); this.submissionError.set('');
    this.submitRequest = this.http.post('/api/analyses', { repository_url: url }, {
      headers: { 'Accept': 'application/json', 'Content-Type': 'application/json', 'Idempotency-Key': this.pending.key },
      observe: 'response', responseType: 'text',
    }).pipe(timeout(10000)).subscribe({
      next: response => {
        this.submitting.set(false);
        try {
          if (response.status !== 202) throw new Error();
          const submitted = decodeSubmission(response.body!);
          const hash = `#analysis/${submitted.id}`;
          if (location.hash === hash) this.view(submitted.id); else location.hash = hash;
        } catch { this.submissionError.set('A resposta do envio não pôde ser validada. Repita o envio para recuperar a mesma análise.'); }
      },
      error: error => {
        this.submitting.set(false); this.waitAfter(error);
        this.submissionError.set(this.errorMessage(error, 'O envio não foi confirmado. Repita o envio com a mesma URL para recuperar a análise sem duplicá-la.'));
      },
    });
  }
  newAnalysis(): void {
    this.submitRequest?.unsubscribe(); this.submitting.set(false); this.pending = null;
    try { sessionStorage.removeItem('analysis-submission-v1'); } catch { /* Optional storage. */ }
    this.acknowledged.set(false); this.submissionError.set('');
    if (location.hash) location.hash = ''; else this.stopViewing();
  }
  private openHash(): void {
    this.submitRequest?.unsubscribe(); this.submitting.set(false);
    const match = /^#analysis\/(.+)$/.exec(location.hash);
    if (!match) { this.stopViewing(); if (location.hash) this.statusError.set('Link de análise inválido.'); return; }
    if (!UUID.test(match[1])) { this.stopViewing(); this.statusError.set('Identificador de análise inválido.'); return; }
    this.view(match[1]);
  }
  private stopViewing(): void {
    this.viewVersion++; clearTimeout(this.pollTimer); this.statusRequest?.unsubscribe(); this.resultsRequest?.unsubscribe();
    this.analysis.set(null); this.analysisId.set(''); this.page.set(null); this.statusError.set(''); this.resultsError.set('');
    this.statusLoading.set(false); this.resultsLoading.set(false); this.paused.set(false);
  }
  private view(id: string): void {
    this.stopViewing(); this.analysisId.set(id); this.pollDelay = 2000; this.failures = 0; this.readStatus();
  }
  resume(): void { clearTimeout(this.pollTimer); this.paused.set(false); this.failures = 0; this.pollDelay = 2000; this.readStatus(); }
  private readStatus(): void {
    if (!this.analysisId() || this.statusLoading()) return;
    const id = this.analysisId(), version = this.viewVersion;
    this.statusLoading.set(true); this.statusError.set('');
    this.statusRequest = this.http.get(`/api/analyses/${id}`, { headers: { Accept: 'application/json' }, observe: 'response', responseType: 'text' })
      .pipe(timeout(10000)).subscribe({
        next: response => {
          if (version !== this.viewVersion) return;
          this.statusLoading.set(false);
          try {
            const analysis = decodeAnalysis(response.body!, id); this.analysis.set(analysis); this.failures = 0;
            if (analysis.status === 'completed') { if (!this.page()) this.loadPage(1); }
            else if (analysis.status !== 'failed') this.schedulePoll(this.pollDelay);
          } catch { this.paused.set(true); this.statusError.set('A resposta de estado não pôde ser validada. Atualize para tentar novamente.'); }
        },
        error: error => {
          if (version !== this.viewVersion) return;
          this.statusLoading.set(false); this.failures++;
          const retryable = !(error instanceof HttpErrorResponse) || [0, 429, 500, 502, 503, 504].includes(error.status);
          this.statusError.set(this.errorMessage(error, 'Não foi possível consultar o estado da análise.'));
          if (retryable && this.failures < 5 && this.retryAfter(error) <= 300000) this.schedulePoll(Math.max(this.pollDelay, this.retryAfter(error)));
          else this.paused.set(true);
        },
      });
  }
  private schedulePoll(delay: number): void {
    clearTimeout(this.pollTimer); this.pollTimer = setTimeout(() => this.readStatus(), delay);
    this.pollDelay = Math.min(this.pollDelay * 2, 10000);
  }
  loadPage(number: number): void {
    const analysis = this.analysis();
    if (!analysis || analysis.status !== 'completed' || !analysis.commit_sha || this.resultsLoading()) return;
    const version = this.viewVersion; this.requestedPage.set(number); this.resultsLoading.set(true); this.resultsError.set('');
    this.resultsRequest = this.http.get(`/api/analyses/${analysis.id}/findings`, {
      headers: { Accept: 'application/json' }, params: { page: number, per_page: this.perPage }, observe: 'response', responseType: 'text',
    }).pipe(timeout(10000)).subscribe({
      next: response => {
        if (version !== this.viewVersion) return;
        this.resultsLoading.set(false);
        try { this.page.set(decodeFindings(response.body!, analysis.id, analysis.commit_sha!, number, this.perPage)); }
        catch { this.resultsError.set('Os resultados não puderam ser validados. Nenhum conteúdo desta resposta foi exibido.'); }
      },
      error: error => { if (version !== this.viewVersion) return; this.resultsLoading.set(false); this.resultsError.set(this.errorMessage(error, 'Não foi possível carregar os achados. Tente novamente.')); },
    });
  }
  failureMessage(code: string): string { return ERRORS[code] ?? 'A análise não pôde ser concluída. Confira a configuração local ou tente uma nova análise.'; }
  private errorMessage(error: unknown, fallback: string): string {
    if (!(error instanceof HttpErrorResponse) || typeof error.error !== 'string') return fallback;
    try { return ERRORS[publicErrorCode(error.error)] ?? fallback; } catch { return fallback; }
  }
  private retryAfter(error: unknown): number {
    if (!(error instanceof HttpErrorResponse)) return 0;
    const header = error.headers.get('Retry-After'); if (!header) return 0;
    const seconds = /^\d+$/.test(header) ? Number(header) : (Date.parse(header) - Date.now()) / 1000;
    // Pause rather than ignore an excessive server cooldown.
    return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds * 1000) : 0;
  }
  private waitAfter(error: unknown): void {
    const wait = this.retryAfter(error); if (!wait) return;
    this.retryUntil.set(Date.now() + wait); clearInterval(this.cooldown);
    const tick = () => { this.secondsLeft.set(Math.max(0, Math.ceil((this.retryUntil() - Date.now()) / 1000))); if (!this.secondsLeft()) clearInterval(this.cooldown); };
    tick(); this.cooldown = setInterval(tick, 1000);
  }
}
bootstrapApplication(AppComponent, { providers: [provideHttpClient(), provideZonelessChangeDetection()] })
  .catch(() => { document.body.textContent = 'Não foi possível iniciar a interface.'; });
