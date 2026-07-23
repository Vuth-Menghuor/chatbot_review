<template>
  <main class="grid min-h-screen bg-[#17485c] lg:grid-cols-[58%_42%]">
    <section
      class="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#17485c] px-4 py-10"
    >
      <div class="absolute inset-0 bg-[#17485c]/94" aria-hidden="true" />
      <AuthLanguageButton />
      <div class="relative z-10 w-full max-w-[480px] text-center">
        <slot />
      </div>
    </section>

    <aside
      class="relative hidden min-h-screen overflow-hidden bg-[url('/gdce-building.png')] bg-cover bg-center lg:block"
    >
      <div class="absolute inset-0 bg-[#0f2f3f]/12" aria-hidden="true" />
    </aside>
  </main>
</template>
