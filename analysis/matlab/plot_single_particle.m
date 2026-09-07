function plot_single_particle
% =========================================================================
%  plot_single_particle.m
%
%  Analyses single-particle tracking data.
%  Each *.txt file must contain exactly 2 columns: x positions, y positions
%  (in pixels).
%
%  Produces THREE figures per file:
%
%   Figure 1 – Phase plot  : Y vs X  (mean-subtracted, µm), coloured by time
%   Figure 2 – X(t)/Y(t)  : x- and y-position vs time (µm)
%   Figure 3 – MSD        : MSD_x and MSD_y vs lag time (log-log, µm²)
% =========================================================================

clear; clc; close all;

%% ---- User settings -------------------------------------------------------
frame_time  = 0.02;      % s per frame  (change to match your acquisition rate)
px_to_um    = 0.065;     % pixel → µm   (change to match your objective/camera)
max_lags    = 2500;      % maximum MSD lag (frames)
skip_initial = 0;        % frames to drop at the very start of each file

%% ---- Aesthetics ----------------------------------------------------------
set(groot, ...
    'defaultAxesFontSize',   12, ...
    'defaultAxesLineWidth',  1.2, ...
    'defaultLineLineWidth',  1.4, ...
    'defaultLineMarkerSize', 4,   ...
    'defaultFigureColor',    'w');

col_x = [0.13 0.47 0.71];   % blue  – x traces / MSD_x
col_y = [0.84 0.19 0.15];   % red   – y traces / MSD_y

%% ---- Discover files -------------------------------------------------------
files = dir('*.txt');
if isempty(files)
    error('No .txt files found in the current directory.');
end

nFiles = numel(files);
fprintf('Found %d .txt file(s).\n\n', nFiles);

%% ---- Loop over files ------------------------------------------------------
for fi = 1:nFiles

    fname = files(fi).name;
    fprintf('[%d/%d]  %s\n', fi, nFiles, fname);

    % -- load data --
    try
        raw = readmatrix(fname);
    catch
        fprintf('  WARNING: readmatrix failed  (skipping)\n');
        continue
    end

    if size(raw, 2) < 2
        fprintf('  WARNING: fewer than 2 columns  (skipping)\n');
        continue
    end

    if size(raw, 1) < 2
        fprintf('  WARNING: fewer than 2 rows  (skipping)\n');
        continue
    end

    % keep only the first two columns (x, y) and skip initial frames
    % for 'creepx' files, skip the first 300 frames on top of skip_initial
    creepx_skip = 300 * contains(fname, 'creepx', 'IgnoreCase', true);
    idx0 = max(1, 1 + skip_initial + creepx_skip);
    raw  = raw(idx0:end, 1:2);

    % pixel → µm, then zero-mean
    pos = raw * px_to_um;
    pos = pos - mean(pos, 1, 'omitnan');

    X = pos(:, 1);
    Y = pos(:, 2);
    N = numel(X);

    t = (0 : N-1).' * frame_time;

    % -- MSD -----------------------------------------------------------------
    L    = min(max_lags, N - 1);
    tau  = (1:L).' * frame_time;
    MSDx = msd1d(X, L);
    MSDy = msd1d(Y, L);

    % -- short base name for figure titles -----------------------------------
    [~, base, ~] = fileparts(fname);
    titleStr = base;

    % =========================================================================
    %  Figure 1 – Phase plot (coloured by time)
    % =========================================================================
    figure('Name',        sprintf('Phase: %s', fname), ...
           'NumberTitle', 'off', ...
           'Position',    [100 500 560 480]);

    ax1 = axes;
    scatter(ax1, X, Y, 3, (1:N).', 'filled');
    colormap(ax1, parula(256));

    cb = colorbar(ax1);
    cb.Label.String = 'time  (s)';
    cb.Ticks = linspace(1, N, 6);
    cb.TickLabels = arrayfun(@(v) sprintf('%.1f', (v-1)*frame_time), ...
                             cb.Ticks, 'UniformOutput', false);

    axis(ax1, 'equal');
    grid(ax1, 'on');  box(ax1, 'on');

    Lim = max(abs([X; Y]));
    if Lim == 0 || ~isfinite(Lim), Lim = 1; end
    xlim(ax1, [-1 1] * Lim * 1.05);
    ylim(ax1, [-1 1] * Lim * 1.05);

    xlabel(ax1, 'x  (µm)');
    ylabel(ax1, 'y  (µm)');
    title(ax1, titleStr, 'Interpreter', 'none', 'FontSize', 10);

    % =========================================================================
    %  Figure 2 – X(t) and Y(t)
    % =========================================================================
    figure('Name',        sprintf('X(t): %s', fname), ...
           'NumberTitle', 'off', ...
           'Position',    [130 320 860 380]);

    ax2 = axes;
    hold(ax2, 'on');
    plot(ax2, t, X, '-',  'Color', col_x, 'DisplayName', 'x(t)');
    plot(ax2, t, Y, '--', 'Color', col_y, 'DisplayName', 'y(t)');
    hold(ax2, 'off');

    grid(ax2, 'on');  box(ax2, 'on');
    xlabel(ax2, 'time  (s)');
    ylabel(ax2, 'position  (µm)');
    title(ax2, titleStr, 'Interpreter', 'none', 'FontSize', 10);
    legend(ax2, 'Location', 'best');

    % =========================================================================
    %  Figure 3 – MSD (log-log)
    % =========================================================================
    figure('Name',        sprintf('MSD: %s', fname), ...
           'NumberTitle', 'off', ...
           'Position',    [160 140 600 460]);

    ax3 = axes;
    hold(ax3, 'on');

    validx = MSDx > 0 & isfinite(MSDx);
    validy = MSDy > 0 & isfinite(MSDy);

    if any(validx)
        loglog(ax3, tau(validx), MSDx(validx), '-',  ...
               'Color', col_x, 'DisplayName', 'MSD_x');
    end
    if any(validy)
        loglog(ax3, tau(validy), MSDy(validy), '--', ...
               'Color', col_y, 'DisplayName', 'MSD_y');
    end

    % reference slope-1 line (purely diffusive)
    if any(validx)
        t_ref = tau([1 end]);
        ref_y = MSDx(find(validx, 1)) * (t_ref / tau(find(validx, 1)));
        loglog(ax3, t_ref, ref_y, ':', ...
               'Color', [0.6 0.6 0.6], 'LineWidth', 1.0, ...
               'DisplayName', 'slope 1');
    end

    hold(ax3, 'off');
    grid(ax3, 'on');  box(ax3, 'on');
    set(ax3, 'XScale', 'log', 'YScale', 'log');
    xlabel(ax3, '\tau  (s)');
    ylabel(ax3, 'MSD  (µm^2)');
    title(ax3, titleStr, 'Interpreter', 'none', 'FontSize', 10);
    legend(ax3, 'Location', 'best');

    % auto-scale y axis to the data
    all_msd = [MSDx(validx); MSDy(validy)];
    if ~isempty(all_msd)
        ylim(ax3, [min(all_msd) * 0.5, max(all_msd) * 2]);
    end

end % file loop

fprintf('\nDone.\n');
end


%% ==========================================================================
%  Local helper
%% ==========================================================================

function MSD = msd1d(traj, L)
% Compute 1-D MSD up to lag L.
% Returns a column vector of length L: MSD(lag=1) … MSD(lag=L).
    N = numel(traj);
    L = min(L, N - 1);
    if L < 1
        MSD = zeros(0, 1);
        return
    end
    MSD = arrayfun(@(lag) ...
              mean((traj(1:end-lag) - traj(1+lag:end)).^2, 'omitnan'), ...
          1:L);
    MSD = MSD(:);
end