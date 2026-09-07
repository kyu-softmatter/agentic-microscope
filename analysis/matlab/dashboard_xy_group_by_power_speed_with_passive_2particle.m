function dashboard_xy_group_by_power_speed_with_passive

clear; clc; close all;

%% ---- User settings ----
frame_time   = 0.02;
px_to_um     = 0.065;
max_lags     = 5000;
skip_initial = 0;

lambda = 5.5;
D      = 5;

meanpos2 = [3.1294, 3.0684];
meanpos3 = [3.1453, 3.0619];

set(groot,'defaultAxesFontSize',12,...
    'defaultAxesLineWidth',1.2,...
    'defaultLineLineWidth',1.5,...
    'defaultLineMarkerSize',5,...
    'defaultFigureColor','w');

colPassive = [0.15 0.15 0.15];
lw_passive = 2.4;
lw_flow    = 1.8;

bead_labels = {'Left','Right'};
bead_cols   = [1, 3];

%% ---- Discover files ----
files = dir('*.txt');
if isempty(files), error('No .txt files found.'); end

entries = [];
bad = {};
for i = 1:numel(files)
    fname = files(i).name;
    try
        meta       = parse_meta_from_filename(fname);
        meta.fname = fname;
        entries    = [entries; meta]; %#ok<AGROW>
    catch ME
        bad{end+1} = sprintf('%s  (%s)', fname, ME.message); %#ok<AGROW>
    end
end

if isempty(entries), error('No files parsed. Check filename format.'); end
if ~isempty(bad)
    fprintf('WARNING: %d files skipped:\n', numel(bad));
    for k = 1:numel(bad), fprintf('  - %s\n', bad{k}); end
end

powers = sort(unique([entries.power].'));
fprintf('Found %d unique powers.\n', numel(powers));
disp(powers);

%% ---- Build per-(power,speed) groups ----
allP = [entries.power].';
allV = [entries.speed_umps].';

[~, ~, gid] = unique([allP, allV], 'rows', 'stable');
u_tbl = unique([allP, allV, gid], 'rows', 'stable');

Groups = cell(2,1);
for b = 1:2
    Groups{b} = struct('power',{},'speed',{},'Wi',{},'files',{},'Xp',{},'Yp',{}, ...
                       'MSDx_cells',{},'MSDy_cells',{},'tau',{},...
                       'MSDx_mean',{},'MSDy_mean',{});
end

for r = 1:size(u_tbl,1)
    P  = u_tbl(r,1);
    V  = u_tbl(r,2);
    Wi = lambda * V / D;
    mask      = (allP == P) & (allV == V);
    fileList  = {entries(mask).fname};
    isPassive = (V == 0);
    for b = 1:2
        G = process_group(fileList, P, V, Wi, bead_cols(b), isPassive, ...
                          px_to_um, skip_initial, meanpos2, meanpos3, ...
                          max_lags, frame_time);
        Groups{b}(end+1) = G; %#ok<AGROW>
    end
end

%% ---- Global Wi->color map ----
allSpeeds  = unique([Groups{1}.speed].');
flowSpeeds = sort(allSpeeds(allSpeeds > 0));
flowWi     = lambda * flowSpeeds / D;

base_cmap = turbo(256);
cmap      = base_cmap(50:256, :);

if isempty(flowWi)
    Wi_min = 0; Wi_max = 1;
else
    Wi_min = min(flowWi); Wi_max = max(flowWi);
    if Wi_max == Wi_min, Wi_max = Wi_min + eps; end
end

Wi_to_color = @(Wi) Wi_color(Wi, flowWi, cmap, Wi_min, Wi_max);

%% ===== Figure 1: Phase plots per power =====
for ip = 1:numel(powers)
    P = powers(ip);

    % ---- Collect data for BOTH beads at this power ----
    % Also compute GLOBAL shared x/y limits across all beads & speeds
    GpBead = cell(2,1);
    for b = 1:2
        Gall  = Groups{b};
        gmask = arrayfun(@(g) g.power == P, Gall);
        Gp    = Gall(gmask);
        if ~isempty(Gp)
            speeds  = [Gp.speed].';
            groupWi = [Gp.Wi].';
            [~, ord] = sortrows([speeds==0, groupWi], [-1 2]);
            Gp = Gp(ord);
        end
        GpBead{b} = Gp;
    end

    % Global phase limits: pool ALL x and y across both beads
    allXY = [];
    for b = 1:2
        for j = 1:numel(GpBead{b})
            allXY = [allXY; GpBead{b}(j).Xp; GpBead{b}(j).Yp]; %#ok<AGROW>
        end
    end
    if isempty(allXY)
        Lxy = 1;
    else
        Lxy = max(abs(allXY));
    end
    lim_phase = [-1,1] .* (1.05 * max(Lxy, 1e-3));

    fig1 = figure('Name', sprintf('Phase plots: P=%.4g', P), ...
                  'NumberTitle','off', 'Position', [50 50 1500 700], 'Color','w');
    outer = tiledlayout(fig1, 1, 2, 'TileSpacing','compact', 'Padding','compact');

    for b = 1:2
        Gp = GpBead{b};

        axParent = nexttile(outer);
        if isempty(Gp)
            axis(axParent,'off');
            title(axParent, sprintf('%s bead (no data)', bead_labels{b}));
            continue;
        end

        drawnow;
        axPos = axParent.Position;
        delete(axParent);

        beadPanel = uipanel(fig1, ...
            'Units','normalized', 'Position', axPos, ...
            'BorderType','none', 'BackgroundColor','w', ...
            'Title', sprintf('%s bead', bead_labels{b}), 'FontSize', 13);

        nTiles = numel(Gp);
        ncol_t = min(4, nTiles);
        nrow_t = ceil(nTiles / ncol_t);
        tl = tiledlayout(beadPanel, nrow_t, ncol_t, ...
                         'TileSpacing','compact', 'Padding','compact');

        for j = 1:nTiles
            ax = nexttile(tl);
            X = Gp(j).Xp;
            Y = Gp(j).Yp;

            if isempty(X)
                text(ax, 0.5, 0.5, '(no data)', 'HorizontalAlignment','center');
                axis(ax,'off');
                title(ax, group_title(Gp(j)));
                continue;
            end

            c = colPassive;
            if Gp(j).speed > 0, c = Wi_to_color(Gp(j).Wi); end

            plot(ax, X, Y, '.', 'Color', c, 'MarkerSize', 4);
            axis(ax,'equal');
            grid(ax,'on'); box(ax,'on');
            xlim(ax, lim_phase);   % <-- shared limits
            ylim(ax, lim_phase);   % <-- shared limits
            xlabel(ax, 'x (\mum)'); ylabel(ax, 'y (\mum)');
            title(ax, group_title(Gp(j)), 'Interpreter','tex');
        end
    end

    if ~isempty(flowWi)
        colormap(cmap);
        cb = colorbar;
        cb.Position = [0.93 0.15 0.015 0.7];
        caxis([Wi_min Wi_max]);
        cb.Label.String = 'Wi'; cb.FontSize = 11; cb.Label.FontSize = 12;
        if numel(flowWi) <= 12
            cb.Ticks      = flowWi;
            cb.TickLabels = arrayfun(@(x) sprintf('%.3g',x), flowWi, 'UniformOutput',false);
        end
    end

    sgtitle(outer, sprintf('Phase plots — P=%.4g', P), 'FontSize', 15);
end

%% ===== Figure 2: MSD per power =====
for ip = 1:numel(powers)
    P = powers(ip);

    % ---- Pre-collect MSD data for both beads to find shared axis limits ----
    GpBead = cell(2,1);
    for b = 1:2
        Gall  = Groups{b};
        gmask = arrayfun(@(g) g.power == P, Gall);
        Gp    = Gall(gmask);
        if ~isempty(Gp)
            speeds  = [Gp.speed].';
            groupWi = [Gp.Wi].';
            [~, ord] = sortrows([speeds==0, groupWi], [-1 2]);
            Gp = Gp(ord);
        end
        GpBead{b} = Gp;
    end

    % Global MSD limits: pool all tau, MSDx, MSDy across both beads
    all_tau_vals = [];
    all_msd_vals = [];
    for b = 1:2
        for j = 1:numel(GpBead{b})
            G = GpBead{b}(j);
            if isempty(G.tau) || isempty(G.MSDx_mean), continue; end
            all_tau_vals = [all_tau_vals; G.tau(2:end)];         %#ok<AGROW>
            all_msd_vals = [all_msd_vals; G.MSDx_mean(2:end);    %#ok<AGROW>
                                          G.MSDy_mean(2:end)];
        end
    end

    if isempty(all_tau_vals)
        xlim_msd = [1e-3 1e3];
        ylim_msd = [1e-5 1e3];
    else
        valid_msd = all_msd_vals(isfinite(all_msd_vals) & all_msd_vals > 0);
        valid_tau = all_tau_vals(isfinite(all_tau_vals) & all_tau_vals > 0);
        if isempty(valid_tau) || isempty(valid_msd)
            xlim_msd = [1e-3 1e3];
            ylim_msd = [1e-5 1e3];
        else
            xlim_msd = [min(valid_tau)*0.9,  max(valid_tau)*1.1];
            ylim_msd = [min(valid_msd)*0.5,  max(valid_msd)*2.0];
        end
    end

    fig2 = figure('Name', sprintf('MSD: P=%.4g', P), ...
                  'NumberTitle','off', 'Position', [80 80 1400 550], 'Color','w');
    outer = tiledlayout(fig2, 1, 2, 'TileSpacing','compact', 'Padding','compact');
    outer.Position = [0.05 0.08 0.85 0.85];

    for b = 1:2
        Gp = GpBead{b};
        ax = nexttile(outer);

        if isempty(Gp)
            axis(ax,'off');
            title(ax, sprintf('%s bead (no data)', bead_labels{b}));
            continue;
        end

        hold(ax,'on'); grid(ax,'on'); box(ax,'on');
        set(ax, 'XScale','log', 'YScale','log', 'FontSize',11);
        xlabel(ax, 't (s)'); ylabel(ax, 'MSD (\mum^2)');
        title(ax, sprintf('%s bead | P=%.4g', bead_labels{b}, P));
        xlim(ax, xlim_msd);   % <-- shared limits
        ylim(ax, ylim_msd);   % <-- shared limits

        % Common tau range within this bead's groups
        taus = {Gp.tau};
        taus = taus(~cellfun(@isempty, taus));
        if isempty(taus), continue; end
        % L_common = min(cellfun(@numel, taus));
        % tau      = taus{1}(1:L_common);

        for j = 1:numel(Gp)
            if isempty(Gp(j).tau) || isempty(Gp(j).MSDx_mean), continue; end
            mx = Gp(j).MSDx_mean;
            my = Gp(j).MSDy_mean;
            tau = Gp(j).tau;

            if Gp(j).speed == 0
                c  = colPassive; lw = lw_passive;
                loglog(ax, tau(2:end), mx(2:end), '-',  'Color',c, 'LineWidth',lw, ...
                    'DisplayName', sprintf('x passive (N=%d)', numel(Gp(j).MSDx_cells)));
                loglog(ax, tau(2:end), my(2:end), '--', 'Color',c, 'LineWidth',lw, ...
                    'DisplayName', sprintf('y passive (N=%d)', numel(Gp(j).MSDy_cells)));
            else
                c  = Wi_to_color(Gp(j).Wi); lw = lw_flow;
                loglog(ax, tau(2:end), mx(2:end), '-',  'Color',c, 'LineWidth',lw, ...
                    'DisplayName', sprintf('x Wi=%.3g (N=%d)', Gp(j).Wi, numel(Gp(j).MSDx_cells)));
                loglog(ax, tau(2:end), my(2:end), '--', 'Color',c, 'LineWidth',lw, ...
                    'DisplayName', sprintf('y Wi=%.3g (N=%d)', Gp(j).Wi, numel(Gp(j).MSDy_cells)));
            end
        end

        legend(ax, 'Location','best');
    end

    if ~isempty(flowWi)
        colormap(cmap);
        cb = colorbar;
        cb.Position = [0.93 0.15 0.015 0.7];
        caxis([Wi_min Wi_max]);
        cb.Label.String = 'Wi'; cb.FontSize = 11; cb.Label.FontSize = 12;
        if numel(flowWi) <= 12
            cb.Ticks      = flowWi;
            cb.TickLabels = arrayfun(@(x) sprintf('%.3g',x), flowWi, 'UniformOutput',false);
        end
    end

    sgtitle(outer, sprintf('MSD_x & MSD_y — P=%.4g', P), 'FontSize', 15);
end

end % main


%% ===================== Helpers (unchanged) =====================

function G = process_group(fileList, P, V, Wi, bead_col, isPassive, ...
                            px_to_um, skip_initial, meanpos2, meanpos3, ...
                            max_lags, frame_time)
    X_all = []; Y_all = [];
    MSDx_cells = {}; MSDy_cells = {};

    for k = 1:numel(fileList)
        fname = fileList{k};
        S = load_and_center(fname, px_to_um, skip_initial, ...
                            meanpos2, meanpos3, bead_col, isPassive);
        pos = S.pos;
        N   = size(pos,1);
        if N < 2
            warning('File %s bead_col=%d has <2 samples; skipping.', fname, bead_col);
            continue;
        end
        X = pos(:,1) - mean(pos(:,1),'omitnan');
        Y = pos(:,2) - mean(pos(:,2),'omitnan');
        X_all = [X_all; X]; %#ok<AGROW>
        Y_all = [Y_all; Y]; %#ok<AGROW>
        L = min(max_lags, N-1);
        if L < 1, continue; end
        MSDx_cells{end+1} = msd1d(X, L); %#ok<AGROW>
        MSDy_cells{end+1} = msd1d(Y, L); %#ok<AGROW>
    end

    tau = []; MSDx_mean = []; MSDy_mean = [];
    if ~isempty(MSDx_cells)
        L_each   = cellfun(@numel, MSDx_cells);
        L_common = min(L_each);
        tau      = (0:L_common-1).' * frame_time;
        nF       = numel(MSDx_cells);
        MSDx_mat = zeros(L_common, nF);
        MSDy_mat = zeros(L_common, nF);
        for k = 1:nF
            MSDx_mat(:,k) = MSDx_cells{k}(1:L_common);
            MSDy_mat(:,k) = MSDy_cells{k}(1:L_common);
        end
        MSDx_mean = mean(MSDx_mat, 2, 'omitnan');
        MSDy_mean = mean(MSDy_mat, 2, 'omitnan');
    end

    G = struct('power',P,'speed',V,'Wi',Wi,'files',{fileList}, ...
               'Xp',X_all,'Yp',Y_all, ...
               'MSDx_cells',{MSDx_cells},'MSDy_cells',{MSDy_cells}, ...
               'tau',tau,'MSDx_mean',MSDx_mean,'MSDy_mean',MSDy_mean);
end


function S = load_and_center(fname, px_to_um, skip_initial, ...
                              meanpos2, meanpos3, bead_col, isPassive)
    dat   = readmatrix(fname);
    x_col = bead_col;
    y_col = bead_col + 1;
    if size(dat,2) < y_col
        error('File %s has only %d columns; need at least %d.', fname, size(dat,2), y_col);
    end
    idx0 = max(1, 1 + skip_initial);
    dat  = dat(idx0:end, :);
    N    = size(dat,1);
    if isPassive
        use_idx = 1:N;
    else
        start_frame = 3000;
        if N < start_frame
            warning('Creepx file %s has only %d frames (<3000); using all.', fname, N);
            use_idx = 1:N;
        else
            use_idx = start_frame:N;
        end
    end
    pos     = dat(use_idx, [x_col, y_col]) * px_to_um;
    preN    = min(10, size(pos,1));
    meanpos = [mean(pos(1:preN,1)), mean(pos(1:preN,2))];
    if     contains(fname,'gly2'), pos = pos - meanpos2;
    elseif contains(fname,'gly3'), pos = pos - meanpos3;
    else,                          pos = pos - meanpos;
    end
    pos  = pos - mean(pos, 1, 'omitnan');
    S.name = fname; S.pos = pos;
end


function s = group_title(G)
    if G.speed == 0
        s = sprintf('PASSIVE | P=%.3g (%d files)', G.power, numel(G.MSDx_cells));
    else
        s = sprintf('Wi=%.3g | P=%.3g (%d)', G.Wi, G.power, numel(G.MSDx_cells));
    end
end


function meta = parse_meta_from_filename(fname)
    [~, base, ~] = fileparts(fname);
    tokens = split(base,'_'); tokens = tokens(:).'; low = lower(tokens);
    isPassive = any(strcmp(low,'passive'));
    if isPassive
        speed_umps = 0;
        idx = find(strcmp(low,'passive'),1,'first');
        if idx >= numel(tokens), error('No token after "passive" for base power.'); end
        basePower = str2double(tokens{idx+1});
        if isnan(basePower), error('Could not parse base power after "passive".'); end
    else
        speedTokIdx = find(endsWith(low,'umps'),1,'first');
        if isempty(speedTokIdx), error('No speed token ending with "umps" found.'); end
        speed_umps = parse_speed_token(tokens{speedTokIdx});
        if speedTokIdx >= numel(tokens), error('No token after speed for base power.'); end
        basePower = str2double(tokens{speedTokIdx+1});
        if isnan(basePower), error('Could not parse base power after speed token.'); end
    end
    OTidx = find(startsWith(low,'ot'),1,'first');
    if isempty(OTidx), error('No OT token found.'); end
    OTfactor = str2double(erase(lower(tokens{OTidx}),'ot'));
    if isnan(OTfactor), error('Could not parse OT factor from %s', tokens{OTidx}); end
    meta = struct('power', basePower * OTfactor, 'speed_umps', speed_umps);
end


function v = parse_speed_token(tok)
    s = lower(tok); s = erase(s,'umps'); s = strrep(s,'p','.');
    v = str2double(s);
    if isnan(v), error('Bad speed token: %s', tok); end
end


function MSD = msd1d(traj, L)
    N = numel(traj); L = min(L, N-1);
    if L < 1, MSD = zeros(0,1); return; end
    MSD = arrayfun(@(lag) mean((traj(1:end-lag)-traj(1+lag:end)).^2,'omitnan'), 1:L);
    MSD = MSD(:); MSD = MSD - MSD(1);
end


function c = Wi_color(Wi, flowWi, cmap, Wi_min, Wi_max)
    if Wi <= 0 || isempty(flowWi), c = [0.2 0.2 0.2]; return; end
    ii = find(abs(flowWi-Wi) < 1e-12, 1);
    if ~isempty(ii) && numel(flowWi) > 1
        t = (ii-1)/(numel(flowWi)-1);
    else
        t = (Wi-Wi_min)/(Wi_max-Wi_min);
    end
    idx = 1 + round(t*(size(cmap,1)-1));
    idx = max(1,min(size(cmap,1),idx));
    c   = cmap(idx,:);
end