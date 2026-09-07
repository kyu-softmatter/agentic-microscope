function dashboard_xy_group_by_power_speed_with_passive
% Group pooled trajectories by (power, speed) AND compare each speed group
% to PASSIVE at the SAME laser power.
%
% NEW EDIT (requested):
%   - Color flow groups by SPEED using a colormap (like your MASTER plot style)
%   - Keep passive in a distinct neutral color
%   - Use the SAME speed->color mapping consistently for phase + MSD figures
%
% Outputs:
%   Figure 1: For each power, a panel that shows:
%       - Passive pooled phase plot
%       - One pooled phase plot per speed (non-passive) at that power
%   Figure 2: For each power, a panel that shows:
%       - MSDx/MSDy passive (same power)
%       - MSDx/MSDy for each speed at that power
%
% Filename patterns (examples):
%   0221_55ldna_5um_passive_0.05_OT0.6_exp20_100x_1.0_3_5um
%   0221_55ldna_5um_creepx_1umps_0.05_OT0.6_exp20_100x_1.0_2_5um
%
% Assumptions:
%   - Passive => speed = 0 (µm/s)
%   - Flow/creep => speed token like "1umps", "0p5umps", "1.5umps"
%   - Power is numeric token immediately after 'passive' OR immediately after speed token
%   - Data are in *.txt files with >=2 columns (x,y) in px.

clear; clc; close all;

%% ---- User settings ----
frame_time   = 0.02;     % s per frame
px_to_um     = 0.065;    % µm / px
max_lags     = 5000;     % MSD lags (per file)
skip_initial = 0;        % frames to skip (applied before windowing)

% Flow windowing (recommended if creep has transients)
use_flow_window = true;
flow_start = 3000;
flow_stop  = 12000;

% Recentering anchors (kept from your prior script)
meanpos2 = [3.1294, 3.0684];
meanpos3 = [3.1453, 3.0619];

% --- Graphics defaults ---
set(groot,'defaultAxesFontSize',12,...
    'defaultAxesLineWidth',1.2,...
    'defaultLineLineWidth',1.5,...
    'defaultLineMarkerSize',5,...
    'defaultFigureColor','w');

% Passive color
colPassive = [0.15 0.15 0.15];

% MSD component styling (we'll keep x solid, y dashed)
% Colors will come from speed colormap
lw_passive = 2.4;
lw_flow    = 1.8;

%% ---- Discover files ----
files = dir('*.txt');
if isempty(files), error('No .txt files found in this folder.'); end

entries = [];
bad = {};
for i = 1:numel(files)
    fname = files(i).name;
    try
        meta = parse_meta_from_filename(fname);
        meta.fname = fname;
        entries = [entries; meta]; %#ok<AGROW>
    catch ME
        bad{end+1} = sprintf('%s  (%s)', fname, ME.message); %#ok<AGROW>
    end
end

if isempty(entries)
    error('No files could be parsed into (power,speed) groups. Check filename format.');
end

if ~isempty(bad)
    fprintf('WARNING: %d files could not be parsed and will be ignored:\n', numel(bad));
    for k = 1:numel(bad), fprintf('  - %s\n', bad{k}); end
end

% Unique powers present
powers = unique([entries.power]');
powers = sort(powers);

fprintf('Found %d unique powers.\n', numel(powers));
disp(powers);

%% ---- Build per-(power,speed) groups ----
allP = [entries.power]';
allV = [entries.speed_umps]';

gid = findgroups(allP, allV);
u = unique(table(allP, allV, gid, 'VariableNames', {'power','speed','gid'}));

Groups = struct('power',{},'speed',{},'files',{},'Xp',{},'Yp',{}, ...
                'MSDx_cells',{},'MSDy_cells',{},'tau',{},'MSDx_mean',{},'MSDy_mean',{});

for r = 1:height(u)
    P = u.power(r);
    V = u.speed(r);
    mask = (allP==P) & (allV==V);
    fileList = {entries(mask).fname};

    G = process_group(fileList, P, V, ...
        px_to_um, skip_initial, meanpos2, meanpos3, ...
        max_lags, frame_time, ...
        use_flow_window, flow_start, flow_stop);

    Groups(end+1) = G; %#ok<AGROW>
end

%% ---- Build a GLOBAL speed->color map (consistent across all powers) ----
allSpeeds = unique([Groups.speed]');
flowSpeeds = allSpeeds(allSpeeds>0);
flowSpeeds = sort(flowSpeeds);

% Choose colormap similar to your other code
base_cmap = turbo(256);
cmap = base_cmap(50:256, :);  % later half

if isempty(flowSpeeds)
    vmin = 0; vmax = 1;
else
    vmin = min(flowSpeeds);
    vmax = max(flowSpeeds);
    if vmax == vmin, vmax = vmin + eps; end
end

speed_to_color = @(v) speed_color(v, flowSpeeds, cmap, vmin, vmax);

%% ===== Figure 1: Phase plots per power (passive vs each speed) =====
for ip = 1:numel(powers)
    P = powers(ip);

    % groups at this power
    gmask = arrayfun(@(g) g.power==P, Groups);
    Gp = Groups(gmask);

    if isempty(Gp), continue; end

    hasPassive = any(arrayfun(@(g) g.speed==0, Gp));
    if ~hasPassive
        warning('No passive files found for power %.4g. Phase/MSD will be speed-only.', P);
    end

    % Order: passive first, then ascending speeds >0
    speeds = [Gp.speed]';
    [~, ord] = sortrows([speeds==0, speeds], [-1 2]); % passive first, then speed ascending
    Gp = Gp(ord);

    % Shared limits for THIS power panel (passive + all speeds)
    allX = vertcat(Gp.Xp);
    allY = vertcat(Gp.Yp);
    Lxy = max([abs(allX); abs(allY)]);
    lim_shared = [-1,1].*(1.05*max(Lxy,1e-3));

    nTiles = numel(Gp);
    ncol = min(4, nTiles);
    nrow = ceil(nTiles/ncol);

    fig = figure('Name',sprintf('Phase plots: P=%.4g',P),'NumberTitle','off');
    tiledlayout(fig, nrow, ncol, 'TileSpacing','compact','Padding','compact');

    for j = 1:nTiles
        nexttile;
        X = Gp(j).Xp; Y = Gp(j).Yp;

        if isempty(X)
            text(0.5,0.5,'(no data)','HorizontalAlignment','center');
            axis off;
            title(group_title(Gp(j)));
            continue;
        end

        if Gp(j).speed==0
            c = colPassive;
        else
            c = speed_to_color(Gp(j).speed);
        end

        plot(X, Y, '.', 'Color', c, 'MarkerSize', 4);

        axis equal; grid on; box on;
        xlim(lim_shared); ylim(lim_shared);
        xlabel('x (\mum)'); ylabel('y (\mum)');
        title(group_title(Gp(j)));
    end

    % Optional: colorbar for speeds (only meaningful if flowSpeeds exist)
    if ~isempty(flowSpeeds)
        colormap(cmap);
        cb = colorbar;
        caxis([vmin vmax]);
        cb.Label.String = 'Speed (\mum/s)';
        cb.FontSize = 11;
        cb.Label.FontSize = 12;

        % Put ticks at actual speeds (if not too many)
        if numel(flowSpeeds) <= 12
            cb.Ticks = flowSpeeds;
            cb.TickLabels = arrayfun(@(x) sprintf('%.3g', x), flowSpeeds, 'UniformOutput', false);
        end
    end
end

%% ===== Figure 2: MSD per power (overlay passive + each speed) =====
for ip = 1:numel(powers)
    P = powers(ip);

    % groups at this power
    gmask = arrayfun(@(g) g.power==P, Groups);
    Gp = Groups(gmask);
    if isempty(Gp), continue; end

    % Order: passive first, then speed ascending
    speeds = [Gp.speed]';
    [~, ord] = sortrows([speeds==0, speeds], [-1 2]);
    Gp = Gp(ord);

    fig = figure('Name',sprintf('MSD: P=%.4g (passive vs speeds)',P),'NumberTitle','off');
    hold on;

    % Choose a common tau range among groups (so axes are comparable)
    taus = {Gp.tau};
    taus = taus(~cellfun(@isempty, taus));
    if isempty(taus)
        warning('No MSD available for power %.4g', P);
        close(fig);
        continue;
    end
    L_common = min(cellfun(@numel, taus));
    tau = taus{1}(1:L_common);

    for j = 1:numel(Gp)
        if isempty(Gp(j).tau) || isempty(Gp(j).MSDx_mean), continue; end

        mx = Gp(j).MSDx_mean(1:L_common);
        my = Gp(j).MSDy_mean(1:L_common);

        if Gp(j).speed==0
            c = colPassive;
            % passive: x solid, y dashed (both same neutral color)
            loglog(tau(2:end), mx(2:end), '-', 'Color', c, 'LineWidth', lw_passive, ...
                'DisplayName', sprintf('x passive (N=%d)', numel(Gp(j).MSDx_cells)));
            loglog(tau(2:end), my(2:end), '--', 'Color', c, 'LineWidth', lw_passive, ...
                'DisplayName', sprintf('y passive (N=%d)', numel(Gp(j).MSDx_cells)));
        else
            v = Gp(j).speed;
            Wi = 1.4.*v;
            c = speed_to_color(v);
            % flow: x solid, y dashed, same speed color
            loglog(tau(2:end), mx(2:end), '-', 'Color', c, 'LineWidth', lw_flow, ...
                'DisplayName', sprintf('x Wi=%.3g (N=%d)', Wi, numel(Gp(j).MSDx_cells)));
            loglog(tau(2:end), my(2:end), '--', 'Color', c, 'LineWidth', lw_flow, ...
                'DisplayName', sprintf('y Wi=%.3g (N=%d)', Wi, numel(Gp(j).MSDx_cells)));
        end
    end

    grid on; box on;
    xlabel('t (s)');
    ylabel('MSD (\mum^2)');
    title(sprintf('Averaged MSD_x & MSD_y at P=%.4g (passive vs speeds)', P));
    legend('Location','best');
    yscale('log'); xscale('log');

    if ~isempty(flowSpeeds)
        colormap(cmap);
        cb = colorbar;
        caxis([vmin vmax]);
        cb.Label.String = 'Speed (\mum/s)';
        cb.FontSize = 11;
        cb.Label.FontSize = 12;

        if numel(flowSpeeds) <= 12
            cb.Ticks = flowSpeeds;
            cb.TickLabels = arrayfun(@(x) sprintf('%.3g', x), flowSpeeds, 'UniformOutput', false);
        end
    end
end

end

%% ===================== Helpers =====================

function G = process_group(fileList, P, V, px_to_um, skip_initial, meanpos2, meanpos3, ...
                           max_lags, frame_time, use_flow_window, flow_start, flow_stop)
% Process all files in this (power, speed) group.

    X_all = []; Y_all = [];
    MSDx_cells = {}; MSDy_cells = {};

    for k = 1:numel(fileList)
        fname = fileList{k};

        S = load_and_center(fname, px_to_um, skip_initial, meanpos2, meanpos3);
        pos = S.pos;
        N = size(pos,1);
        if N < 2
            warning('File %s has <2 samples; skipping.', fname);
            continue;
        end

        isPassive = contains(lower(fname), 'passive');

        if isPassive || ~use_flow_window
            idx = 1:N;
        else
            if N < flow_start
                warning('Flow file %s shorter than %d frames; using all frames.', fname, flow_start);
                idx = 1:N;
            else
                idx = flow_start : min(flow_stop, N);
            end
        end

        X = pos(idx,1);
        Y = pos(idx,2);

        % file-wise demean after windowing
        X = X - mean(X,'omitnan');
        Y = Y - mean(Y,'omitnan');

        X_all = [X_all; X]; %#ok<AGROW>
        Y_all = [Y_all; Y]; %#ok<AGROW>

        Nw = numel(X);
        L = min(max_lags, Nw-1);
        if L < 1
            warning('File %s window too short for MSD; skipping MSD.', fname);
            continue;
        end
        MSDx_cells{end+1} = msd1d(X, L); %#ok<AGROW>
        MSDy_cells{end+1} = msd1d(Y, L); %#ok<AGROW>
    end

    % Average MSD within group
    tau = [];
    MSDx_mean = [];
    MSDy_mean = [];
    if ~isempty(MSDx_cells)
        L_each = cellfun(@numel, MSDx_cells);
        L_common = min(L_each);
        tau = (0:L_common-1)' * frame_time;

        nF = numel(MSDx_cells);
        MSDx_mat = zeros(L_common, nF);
        MSDy_mat = zeros(L_common, nF);
        for k = 1:nF
            MSDx_mat(:,k) = MSDx_cells{k}(1:L_common);
            MSDy_mat(:,k) = MSDy_cells{k}(1:L_common);
        end
        MSDx_mean = mean(MSDx_mat, 2, 'omitnan');
        MSDy_mean = mean(MSDy_mat, 2, 'omitnan');
    end

    G = struct();
    G.power = P;
    G.speed = V;
    G.files = fileList;
    G.Xp = X_all;
    G.Yp = Y_all;
    G.MSDx_cells = MSDx_cells;
    G.MSDy_cells = MSDy_cells;
    G.tau = tau;
    G.MSDx_mean = MSDx_mean;
    G.MSDy_mean = MSDy_mean;
end

function s = group_title(G)
    if G.speed == 0
        s = sprintf('PASSIVE | P=%.3g (%d files)', G.power, numel(G.MSDx_cells));
    else
        s = sprintf('v=%.3g \\mum/s | P=%.3g (%d files)', G.speed, G.power, numel(G.MSDx_cells));
    end
end

function meta = parse_meta_from_filename(fname)
% Extract:
%   speed (µm/s)
%   effective power = (base power) * (OT factor)
%
% Example:
%   passive_0.05_OT0.6  → power = 0.05 * 0.6

    [~, base, ~] = fileparts(fname);
    tokens = split(base, '_');
    tokens = tokens(:)';

    low = lower(tokens);

    %% -------- Extract speed --------
    isPassive = any(strcmp(low,'passive'));

    if isPassive
        speed_umps = 0;
        idx = find(strcmp(low,'passive'),1,'first');
        if idx >= numel(tokens)
            error('No token after "passive" to parse base power.');
        end
        basePower = str2double(tokens{idx+1});
        if isnan(basePower)
            error('Could not parse base power after "passive".');
        end
    else
        % find speed token like "1umps"
        speedTokIdx = find(endsWith(low,'umps'),1,'first');
        if isempty(speedTokIdx)
            error('No speed token ending with "umps" found.');
        end
        speed_umps = parse_speed_token(tokens{speedTokIdx});

        if speedTokIdx >= numel(tokens)
            error('No token after speed to parse base power.');
        end
        basePower = str2double(tokens{speedTokIdx+1});
        if isnan(basePower)
            error('Could not parse base power after speed token.');
        end
    end

    %% -------- Extract OT factor --------
    OTidx = find(startsWith(low,'ot'),1,'first');
    if isempty(OTidx)
        error('No OT token (e.g., OT0.6) found in filename.');
    end

    OTtoken = tokens{OTidx};   % e.g. 'OT0.6'
    OTfactor = str2double(erase(lower(OTtoken),'ot'));
    if isnan(OTfactor)
        error('Could not parse OT factor from %s', OTtoken);
    end

    %% -------- Effective power --------
    power = basePower * OTfactor;

    meta = struct('power', power, ...
                  'speed_umps', speed_umps);
end

function v = parse_speed_token(tok)
% tok examples: "1umps", "0p5umps", "1.5umps"
    s = lower(tok);
    s = erase(s, 'umps');     % now like "1" or "0p5" or "1.5"
    s = strrep(s, 'p', '.');  % "0p5" -> "0.5"
    v = str2double(s);
    if isnan(v)
        error('Bad speed token: %s', tok);
    end
end

function S = load_and_center(fname, px_to_um, skip_initial, meanpos2, meanpos3)
    dat = load(fname);
    if size(dat,2) < 2
        error('File %s has <2 columns.', fname);
    end

    idx0 = max(1, 1 + skip_initial);
    pos = dat(idx0:end, 1:2) * px_to_um; % to microns

    % Early-frames mean for local centering
    preN = min(10, size(pos,1));
    if preN >= 1
        meanpos = [mean(pos(1:preN,1)), mean(pos(1:preN,2))];
    else
        meanpos = [0, 0];
    end

    % Filename-conditional centering (kept from prior script)
    if contains(fname, 'gly2')
        pos = pos - meanpos2;
    elseif contains(fname, 'gly3')
        pos = pos - meanpos3;
    else
        pos = pos - meanpos;
    end

    % Final global demean
    pos = pos - mean(pos,1,'omitnan');

    S.name = fname;
    S.pos  = pos;
end

function MSD = msd1d(traj, L)
    N = numel(traj);
    L = min(L, N-1);
    if L < 1
        MSD = zeros(0,1);
        return;
    end
    MSD = arrayfun(@(lag) mean((traj(1:end-lag) - traj(1+lag:end)).^2, 'omitnan'), 1:L);
    MSD = MSD(:);
    MSD = MSD - MSD(1);
end

function c = speed_color(v, flowSpeeds, cmap, vmin, vmax)
% Map a speed value to a color.
% - If v is exactly one of the detected flowSpeeds, use its position for stable coloring.
% - Otherwise, map continuously with caxis range.

    if v <= 0 || isempty(flowSpeeds)
        c = [0.2 0.2 0.2];
        return;
    end

    % Prefer discrete mapping if exact match
    ii = find(abs(flowSpeeds - v) < 1e-12, 1);
    if ~isempty(ii) && numel(flowSpeeds) > 1
        t = (ii-1) / (numel(flowSpeeds)-1);
    else
        t = (v - vmin) / (vmax - vmin);
    end

    idx = 1 + round(t * (size(cmap,1)-1));
    idx = max(1, min(size(cmap,1), idx));
    c = cmap(idx,:);
end