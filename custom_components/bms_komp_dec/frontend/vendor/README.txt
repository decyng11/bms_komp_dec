Lokalne kopie Chart.js (opcjonalne)
==================================
Wykres "Przebieg mocy, SOC i cen" korzysta z biblioteki Chart.js. Domyslnie panel pobiera ja z internetu
(cdn.jsdelivr.net). Jesli chcesz, zeby dzialal bez dostepu do internetu w przegladarce, pobierz dwa pliki
i wgraj je do tego folderu (pod dokladnie takimi nazwami):

  1) https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js
        -> chart.umd.min.js
  2) https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js
        -> chartjs-adapter-date-fns.bundle.min.js

Po wgraniu zrestartuj Home Assistanta i odswiez karte (Ctrl+F5). Gdy plikow brak, panel uzywa CDN jak dotychczas.
