(() => {
  const selector = 'script[type="WaveDrom"][data-wavedrom-skin="auto"]';

  function render() {
    const skin = document.documentElement.dataset.mdColorScheme === "slate"
      ? "dark"
      : "default";

    document.querySelectorAll(selector).forEach((element) => {
      element.textContent = element.textContent.trim().replace(
        /\}\s*$/,
        `,\n  config: { skin: "${skin}" }\n}`,
      );
    });

    WaveDrom.ProcessAll();
  }

  window.addEventListener("load", render, { once: true });

  document.addEventListener("change", (event) => {
    if (event.target.closest('[data-md-component="palette"]')) {
      setTimeout(() => window.location.reload(), 0);
    }
  });
})();