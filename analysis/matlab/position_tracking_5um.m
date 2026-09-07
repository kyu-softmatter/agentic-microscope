clear; close all; clc; format long;

%% --- Parameters (edit as needed) ---
frame_time = 0.02;        % seconds per frame (for downstream use if needed)
px_to_um   = 0.065;       % um per pixel (set your correct calibration)
save_in_um = false;       % true -> save [um]; false -> save [pixels]
suffix     = '_5um.txt';  % output suffix to match particle size

% Thresholding / preprocessing
img_cut           = 300;     % fixed threshold; if [], will fall back to Otsu per-frame
use_otsu_fallback = true;    % if fixed threshold yields no pixels, try Otsu
median_filter     = false;   % apply 3x3 median filter to reduce salt-pepper noise
clip_max          = 2000;    % e.g., 2000 to clip very bright pixels; [] disables
min_area_px       = 20^2;    % ignore tiny specks; set 0 to disable

% Tracking mode
use_weighted_centroid = true; % true: intensity-weighted centroid; false: simple mean of mask

% --- Live preview & overlay ---
show_overlay           = false;  % turn on/off the live viewer
overlay_stride         = 1;      % update viewer every N frames
plus_scale_px          = 14;     % "size" of the plus in pixels
plus_linewidth         = 2;      % thickness of the plus lines
preview_autocontrast   = true;   % auto scale display range per frame
preview_stretch_limits = [0.01 0.999]; % percentile stretch for display (0-1)

%% --- Build paths by scanning current directory's subfolders ---
paths = {};

img_patterns = { ...
    '*.tif', '*.tiff', ...
    '*.TIF', '*.TIFF', ...
    '*MMStack*.ome.tif', '*MMStack*.ome.tiff', ...
    '*MMStack*.OME.TIF', '*MMStack*.OME.TIFF' ...
};

D = dir();

fprintf('Scanning first-level subfolders of: %s\n', pwd);

for ii = 1:numel(D)

    if D(ii).isdir && ~startsWith(D(ii).name, '.')
        sub = D(ii).name;

        tfiles = [];

        for p = 1:numel(img_patterns)
            tfiles = [tfiles; dir(fullfile(sub, img_patterns{p}))]; %#ok<AGROW>
        end

        if isempty(tfiles)
            fprintf('  [SKIP] %s: no matching TIF/TIFF.\n', sub);
            continue;
        end

        T = struct2table(tfiles);
        T = sortrows(T, "name");
        tfiles = table2struct(T);

        picked = fullfile(tfiles(1).folder, tfiles(1).name);

        fprintf('  [OK]   %s -> %s\n', sub, tfiles(1).name);

        paths{end+1} = picked; %#ok<SAGROW>
    end
end

if isempty(paths)
    error('No .tif/.tiff files found in first-level subfolders.');
end

%% --- Loop through each file ---
for s = 1:numel(paths)

    img_path = paths{s};

    info = imfinfo(img_path);
    nFrames = numel(info);

    pos = nan(nFrames, 2);

    fprintf('Processing file %d/%d: %s\n', s, numel(paths), img_path);

    % Live viewer handles
    hFig = [];
    hAx = [];
    hImg = [];
    hPlusH = [];
    hPlusV = [];

    for k = 1:nFrames

        I = imread(img_path, k);

        if ~isempty(clip_max)
            I = min(I, cast(clip_max, class(I)));
        end

        Iproc = I;

        if median_filter
            Iproc = medfilt2(Iproc, [3 3]);
        end

        %% --- Show raw video first ---
        if show_overlay && mod(k, overlay_stride) == 0

            if isempty(hFig) || ~isvalid(hFig)

                hFig = figure( ...
                    'Name', sprintf('Preview: %s', img_path), ...
                    'NumberTitle', 'off' ...
                );

                hAx = axes('Parent', hFig);
                colormap(hAx, gray);

                hImg = imshow(I, [], ...
                    'Parent', hAx, ...
                    'InitialMagnification', 'fit' ...
                );

                hold(hAx, 'on');

                hPlusH = plot(hAx, NaN, NaN, ...
                    'r-', ...
                    'LineWidth', plus_linewidth ...
                );

                hPlusV = plot(hAx, NaN, NaN, ...
                    'r-', ...
                    'LineWidth', plus_linewidth ...
                );

            else
                if isvalid(hImg)
                    set(hImg, 'CData', I);
                end
            end

            if preview_autocontrast && isgraphics(hAx)
                try
                    dr01 = stretchlim(I, preview_stretch_limits);
                    clim = double(dr01) * double(intmax(class(I)));
                    set(hAx, 'CLim', clim);
                catch
                    set(hAx, 'CLim', [double(min(I(:))) double(max(I(:)))]);
                end
            end

            title(hAx, ...
                sprintf('%s\nFrame %d / %d', img_path, k, nFrames), ...
                'Interpreter', 'none' ...
            );

            drawnow limitrate nocallbacks;
        end

        %% --- Mask + centroid ---
        if ~isempty(img_cut)
            BW = Iproc > img_cut;
        else
            level = graythresh(Iproc);
            BW = Iproc > uint16(level * double(intmax(class(Iproc))));
        end

        if min_area_px > 0
            BW = bwareaopen(BW, min_area_px);
        end

        if ~any(BW(:)) && use_otsu_fallback
            level = graythresh(Iproc);
            BW = Iproc > uint16(level * double(intmax(class(Iproc))));

            if min_area_px > 0
                BW = bwareaopen(BW, min_area_px);
            end
        end

        if ~any(BW(:))

            if show_overlay && mod(k, overlay_stride) == 0
                set(hPlusH, 'XData', NaN, 'YData', NaN);
                set(hPlusV, 'XData', NaN, 'YData', NaN);
                drawnow limitrate nocallbacks;
            end

            continue;
        end

        CC = bwconncomp(BW);

        if CC.NumObjects > 1
            [~, bigIdx] = max(cellfun(@numel, CC.PixelIdxList));
            BW(:) = 0;
            BW(CC.PixelIdxList{bigIdx}) = 1;
        end

        if use_weighted_centroid

            Id = double(Iproc);
            Id(~BW) = 0;

            [Y, X] = ndgrid(1:size(Iproc, 1), 1:size(Iproc, 2));

            wsum = sum(Id(:));

            if wsum <= 0
                S = regionprops(BW, 'Centroid');

                if ~isempty(S)
                    pos(k, :) = S.Centroid;
                end
            else
                pos(k, :) = [ ...
                    sum(Id(:) .* X(:)) / wsum, ...
                    sum(Id(:) .* Y(:)) / wsum ...
                ];
            end

        else

            S = regionprops(BW, 'Centroid');

            if ~isempty(S)
                pos(k, :) = S.Centroid;
            end

        end

        if mod(k, 500) == 0
            fprintf('  frame %d/%d\n', k, nFrames);
        end

        %% --- Draw red plus ---
        if show_overlay && mod(k, overlay_stride) == 0

            xy = pos(k, :);

            if all(isfinite(xy))

                x = xy(1);
                y = xy(2);
                ps = plus_scale_px;

                set(hPlusH, ...
                    'XData', [x - ps, x + ps], ...
                    'YData', [y, y], ...
                    'Color', 'r', ...
                    'LineWidth', plus_linewidth ...
                );

                set(hPlusV, ...
                    'XData', [x, x], ...
                    'YData', [y - ps, y + ps], ...
                    'Color', 'r', ...
                    'LineWidth', plus_linewidth ...
                );

            else

                set(hPlusH, 'XData', NaN, 'YData', NaN);
                set(hPlusV, 'XData', NaN, 'YData', NaN);

            end

            drawnow limitrate nocallbacks;
        end
    end

    %% --- Save output ---
    startFrame = 1;
    endFrame = min(18000, size(pos, 1));

    pos = pos(startFrame:endFrame, :);

    if save_in_um
        pos = pos * px_to_um;
    end

    % Use the immediate subfolder name, not the image file name.
    % Example:
    %   img_path = 'folder_A/MMStack_Pos0.ome.tif'
    %   out_name = 'folder_A_5um.txt'
    img_folder = fileparts(img_path);
    [~, folder_name] = fileparts(img_folder);

    out_name = [folder_name suffix];

    % If file already exists, append _2, _3, etc. to avoid overwriting.
    if exist(out_name, 'file')

        [~, base_name, ext] = fileparts(out_name);

        counter = 2;

        while exist([base_name '_' num2str(counter) ext], 'file')
            counter = counter + 1;
        end

        out_name = [base_name '_' num2str(counter) ext];
    end

    fid = fopen(out_name, 'w');

    if fid < 0

        warning('Could not open %s for writing.', out_name);

    else

        fprintf(fid, '%.6f\t%.6f\n', pos.');
        fclose(fid);

        fprintf('  -> Saved: %s\n', out_name);

    end
end

fprintf('\nDone.\n');