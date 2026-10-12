(() => {
  const resetVisibility = [];

  document.querySelectorAll('.modern-form input[type="password"]').forEach((input) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'password-field-control';
    input.before(wrapper);
    wrapper.append(input);

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'password-toggle';
    button.setAttribute('aria-controls', input.id);
    const fieldName = input.labels[0]?.textContent.replace(/:\s*$/, '') || 'password';

    const setVisibility = (visible) => {
      input.type = visible ? 'text' : 'password';
      button.textContent = visible ? 'Hide' : 'Show';
      button.setAttribute('aria-label', `${visible ? 'Hide' : 'Show'} ${fieldName}`);
      button.setAttribute('aria-pressed', String(visible));
    };

    setVisibility(false);
    button.addEventListener('click', () => setVisibility(input.type === 'password'));
    input.form.addEventListener('submit', () => setVisibility(false));
    input.form.addEventListener('reset', () => setVisibility(false));
    resetVisibility.push(() => setVisibility(false));
    wrapper.append(button);
  });

  window.addEventListener('pageshow', () => resetVisibility.forEach((reset) => reset()));
})();
