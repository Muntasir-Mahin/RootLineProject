(() => {
  const form = document.querySelector('[data-confirm-logout]');
  if (!form) return;

  const button = form.querySelector('button[type="submit"]');
  const error = form.querySelector('[data-logout-error]');
  let submitting = false;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (submitting) return;
    submitting = true;
    button.disabled = true;
    button.textContent = 'Signing out…';
    error.hidden = true;
    let errorMessage = 'Could not log out. Please try again or reload this page.';

    try {
      const response = await fetch(form.dataset.tokenUrl, {
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) throw new Error('Could not refresh the logout form. Please try again.');
      const data = await response.json();
      if (data.signedOut) {
        window.location.assign(form.dataset.loginUrl);
        return;
      }
      if (String(data.userId) !== form.elements.user_id.value) {
        errorMessage = 'Your signed-in account changed. Reload this page to confirm logout.';
        throw new Error(errorMessage);
      }
      if (typeof data.csrfToken !== 'string') {
        throw new Error('Could not refresh the logout form. Please try again.');
      }
      form.elements.csrfmiddlewaretoken.value = data.csrfToken;
      HTMLFormElement.prototype.submit.call(form);
    } catch {
      error.textContent = errorMessage;
      error.hidden = false;
      button.disabled = false;
      button.textContent = 'Yes, log out';
      submitting = false;
    }
  });
})();
