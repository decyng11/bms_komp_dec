Lokalne kopie Chart.js
======================
Wykres "Przebieg mocy, SOC i cen" korzysta z biblioteki Chart.js. Karta wczytuje ja najpierw z tego folderu,
a gdy plikow brak - z internetu (cdn.jsdelivr.net).

  chart.umd.min.js                         - Chart.js 4.4.1 (licencja MIT, https://www.chartjs.org)
  chartjs-adapter-date-fns.bundle.min.js   - chartjs-adapter-date-fns 3.0.0 z date-fns (licencja MIT)

Pliki pochodza z https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js oraz
https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js
i nie sa objete licencja BMS komp-dec - obowiazuje dla nich licencja MIT ich autorow (informacja
o licencji jest w naglowku kazdego pliku).
