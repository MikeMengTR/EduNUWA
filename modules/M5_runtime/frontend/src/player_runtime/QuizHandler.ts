// DOM-based quiz popup that returns a Promise (H5: blocks playback until answer)
export class QuizHandler {
  private _overlay: HTMLDivElement | null = null;

  show(question: string, options: string[]): Promise<string> {
    this.destroy();

    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'quiz-overlay';
      overlay.innerHTML = `
        <div class="quiz-modal">
          <h2 class="quiz-question">${escapeHtml(question)}</h2>
          <div class="quiz-options">
            ${options.map((opt, i) => `
              <button class="quiz-option" data-index="${i}">${escapeHtml(opt)}</button>
            `).join('')}
          </div>
        </div>
      `;

      overlay.addEventListener('click', (e) => {
        const btn = (e.target as HTMLElement).closest('.quiz-option');
        if (btn) {
          const answer = options[Number((btn as HTMLButtonElement).dataset.index)];
          this.destroy();
          resolve(answer);
        }
      });

      document.body.appendChild(overlay);
      this._overlay = overlay;
    });
  }

  destroy(): void {
    if (this._overlay) {
      this._overlay.remove();
      this._overlay = null;
    }
  }
}

function escapeHtml(s: string): string {
  const el = document.createElement('span');
  el.textContent = s;
  return el.innerHTML;
}
