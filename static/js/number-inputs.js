(() => {
  document.querySelectorAll('.rootline-app input[type="number"]').forEach((input) => {
    if (!input.hasAttribute('inputmode')) input.inputMode = 'decimal';

    // Let the page scroll instead of changing a focused numeric value.
    input.addEventListener('wheel', () => {
      if (document.activeElement === input) input.blur();
    }, { passive: true });

    input.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
        event.preventDefault();
      }
    });
  });
})();
