import { Component, inject, provideZonelessChangeDetection, signal } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { HttpClient, provideHttpClient } from '@angular/common/http';
import { timeout } from 'rxjs';

@Component({
  selector: 'app-root',
  standalone: true,
  template: `<main><h1>AI Software Engineer</h1>
    <p>B02 infrastructure bootstrap</p>
    <p role="status">Application API: {{ apiStatus() }}</p>
    <p>Analysis submission and results are not implemented yet.</p></main>`,
})
class AppComponent {
  readonly apiStatus = signal('checking');
  private readonly http = inject(HttpClient);
  constructor() {
    this.http.get<{ status: string }>('/api/health').pipe(timeout(5000)).subscribe({
      next: (response) => this.apiStatus.set(response.status === 'ok' ? 'ready' : 'unavailable'),
      error: () => this.apiStatus.set('unavailable'),
    });
  }
}
bootstrapApplication(AppComponent, { providers: [provideHttpClient(), provideZonelessChangeDetection()] })
  .catch(() => { document.body.textContent = 'Frontend bootstrap failed.'; });
